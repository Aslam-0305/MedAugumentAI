"""Job queries, cancellation, results and manual review (design §8, §12)."""
from __future__ import annotations

import shutil
from collections import Counter

from ..context import AppContext
from ..utils.common import AppError, not_found, utcnow

TERMINAL = ("completed", "failed", "cancelled")


def get_job(ctx: AppContext, job_id: str, *, full: bool = False) -> dict:
    job = ctx.store.find_one("augmentation_jobs", {"job_id": job_id})
    if not job:
        raise not_found("Job", job_id)
    if not full:
        job = {k: v for k, v in job.items() if k not in ("plan", "trace")} | {"plan_summary": {
            "total_additional": job["plan"]["total_additional"], "warnings": job["plan"]["warnings"], "classes": job["plan"]["classes"]}}
    return job


def list_jobs(ctx: AppContext, dataset_id: str | None = None) -> list[dict]:
    flt = {"dataset_id": dataset_id} if dataset_id else None
    return [{k: v for k, v in j.items() if k in ("job_id", "dataset_id", "name", "modality", "status", "progress", "created_at", "completed_at", "seed")}
            for j in ctx.store.find("augmentation_jobs", flt, sort=[("created_at", -1)])]


def cancel_job(ctx: AppContext, job_id: str) -> dict:
    job = get_job(ctx, job_id)
    if job["status"] in TERMINAL:
        raise AppError(f"Job is already {job['status']}", 409, "conflict")
    ev = ctx.cancel_events.get(job_id)
    if ev:
        ev.set()
    update = {"cancel_requested": True}
    if job["status"] == "queued":
        update.update(status="cancelled")  # the worker skips non-queued jobs when it picks it up
    ctx.store.update_one("augmentation_jobs", {"job_id": job_id}, set=update,
                         push={"logs": {"t": utcnow(), "msg": "Cancellation requested"}})
    return get_job(ctx, job_id)


def job_results(ctx: AppContext, job_id: str, *, status: str | None = None, skip: int = 0, limit: int = 24) -> dict:
    job = get_job(ctx, job_id, full=True)
    flt: dict = {"job_id": job_id}
    all_samples = ctx.store.find("augmented_samples", flt, fields=["sample_id", "labels", "validation_status", "review_status", "validation"])
    def is_usable(s: dict) -> bool:
        return s["validation_status"] != "rejected" and s["review_status"] != "rejected"

    usable = [s for s in all_samples if is_usable(s)]
    gen, rej_auto = Counter(), Counter()
    for s in all_samples:
        (gen if is_usable(s) else rej_auto).update(s["labels"])
    before = {c["label"]: c["original"] for c in job["plan"]["classes"]}
    classes = [{"label": c["label"], "original": c["original"], "target": c["target"], "generated": gen.get(c["label"], 0),
                "rejected": rej_auto.get(c["label"], 0), "final": c["original"] + gen.get(c["label"], 0)} for c in job["plan"]["classes"]]
    msgs = Counter(m for s in all_samples for m in s.get("validation", {}).get("messages", []))
    if status:
        flt["validation_status"] = status
    items = ctx.store.find("augmented_samples", flt, sort=[("sample_id", 1)], skip=skip, limit=min(limit, 200))
    return {
        "job_id": job_id, "status": job["status"], "summary": job.get("summary"), "classes": classes, "before": before,
        "counts": {"total_records": len(all_samples), "usable": len(usable),
                   "passed": sum(s["validation_status"] == "passed" for s in all_samples),
                   "with_warnings": sum(s["validation_status"] == "warning" for s in all_samples),
                   "rejected_by_checks": sum(s["validation_status"] == "rejected" for s in all_samples),
                   "rejected_by_user": sum(s["review_status"] == "rejected" for s in all_samples)},
        "warnings": job["plan"]["warnings"], "validation_messages": [{"message": m, "count": n} for m, n in msgs.most_common(10)],
        "samples": items, "total_filtered": ctx.store.count("augmented_samples", flt),
    }


def get_sample(ctx: AppContext, job_id: str, sample_id: str) -> dict:
    s = ctx.store.find_one("augmented_samples", {"job_id": job_id, "sample_id": sample_id})
    if not s:
        raise not_found("Sample", sample_id)
    return s


def review_sample(ctx: AppContext, job_id: str, sample_id: str, review_status: str) -> dict:
    if review_status not in ("accepted", "rejected", "auto"):
        raise AppError("review_status must be accepted, rejected or auto", 400, "invalid_request")
    s = get_sample(ctx, job_id, sample_id)
    if s["validation_status"] == "rejected" and review_status == "accepted":
        raise AppError("Outputs rejected by technical checks have no file and cannot be accepted", 409, "conflict")
    ctx.store.update_one("augmented_samples", {"job_id": job_id, "sample_id": sample_id}, set={"review_status": review_status})
    return get_sample(ctx, job_id, sample_id)


def delete_job(ctx: AppContext, job_id: str) -> None:
    job = get_job(ctx, job_id)
    if job.get("status") in ("queued", "running"):
        raise AppError("Cancel running job before deleting it", 409, "conflict")
    shutil.rmtree(ctx.storage.augmented_dir(job_id), ignore_errors=True)
    ctx.store.delete_many("augmented_samples", {"job_id": job_id})
    for e in ctx.store.find("exports", {"job_id": job_id}, fields=["export_id"]):
        shutil.rmtree(ctx.storage.export_dir(e["export_id"]), ignore_errors=True)
    ctx.store.delete_many("exports", {"job_id": job_id})
    ctx.store.delete_many("augmentation_jobs", {"job_id": job_id})

