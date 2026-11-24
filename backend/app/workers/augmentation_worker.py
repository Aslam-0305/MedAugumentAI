"""Background augmentation worker.

`run_augmentation_job(ctx, job_id)` is a plain function: today it runs on the app's thread pool
(fine for a local prototype, not a durable queue). To scale out, wrap it in a Celery task that builds
an AppContext from settings — nothing else needs to change.
"""
from __future__ import annotations

import json
import threading
import traceback
from collections import Counter
from pathlib import Path

import numpy as np

from ..context import AppContext
from ..imaging.loaders import load_image_set, save_image
from ..imaging.pipeline import AugmentationPipeline, parse_pipeline_config
from ..imaging.validation import check_lineage, check_output
from ..utils.common import sha256_file, stable_entropy, to_jsonable, utcnow

MAX_RETRIES = 3       # extra attempts with a fresh random stream when an output is rejected
BATCH = 25            # sample records persisted per write
LOG_EVERY = 50


def _log(ctx: AppContext, job_id: str, msg: str) -> None:
    ctx.store.update_one("augmentation_jobs", {"job_id": job_id}, push={"logs": {"t": utcnow(), "msg": msg}}, push_cap=200)


def run_augmentation_job(ctx: AppContext, job_id: str) -> None:
    job = ctx.store.find_one("augmentation_jobs", {"job_id": job_id})
    if not job or job["status"] != "queued":  # cancelled while waiting in the queue
        ctx.cancel_events.pop(job_id, None)
        return
    event = ctx.cancel_events.setdefault(job_id, threading.Event())
    ctx.store.update_one("augmentation_jobs", {"job_id": job_id}, set={"status": "running", "started_at": utcnow()})
    try:
        _run(ctx, job, event)
    except Exception as exc:  # never leave a job stuck in "running"
        _log(ctx, job_id, f"Job failed: {type(exc).__name__}: {exc}")
        ctx.store.update_one("augmentation_jobs", {"job_id": job_id},
                             set={"status": "failed", "error": f"{type(exc).__name__}: {exc}", "completed_at": utcnow(), "trace": traceback.format_exc()[-2000:]})
    finally:
        ctx.cancel_events.pop(job_id, None)


def _run(ctx: AppContext, job: dict, event: threading.Event) -> None:
    store, storage = ctx.store, ctx.storage
    job_id, modality, seed = job["job_id"], job["modality"], job["seed"]
    pcfg, _ = parse_pipeline_config(modality, job["config"]["augmentation"])
    pipeline = AugmentationPipeline(pcfg)
    out_dir = storage.augmented_dir(job_id)
    for sub in ("images", "labels", "provenance", "masks"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    ids = [a["source_image_id"] for a in job["plan"]["assignments"]]
    sources: dict[str, dict] = {}
    for k in range(0, len(ids), 500):
        for d in store.find("images", {"image_id": {"$in": ids[k : k + 500]}}):
            sources[d["image_id"]] = d
    tasks = [(a["source_image_id"], v) for a in job["plan"]["assignments"] for v in range(a["n_variants"])]
    total = len(tasks)
    counts = Counter()
    batch: list[dict] = []
    cache_id, cache_img = None, None
    errors: list[str] = []
    expected = None if pcfg.output_dtype == "preserve" else "float32"
    cancelled = False

    def flush(force: bool = False) -> None:
        if batch and (force or len(batch) >= BATCH):
            store.insert_many("augmented_samples", to_jsonable(list(batch)))
            batch.clear()

    def progress(final: bool = False) -> None:
        done = counts["accepted"] + counts["warnings"] + counts["rejected"] + counts["failed"]
        store.update_one("augmentation_jobs", {"job_id": job_id}, set={"progress": {
            "total": total, "done": done, "accepted": counts["accepted"], "warnings": counts["warnings"],
            "rejected": counts["rejected"], "failed": counts["failed"], "percent": round(100 * done / total, 1) if total else 100.0}})

    for n, (source_id, variant) in enumerate(tasks):
        if event.is_set():
            cancelled = True
            break
        src_doc = sources.get(source_id)
        try:
            if source_id != cache_id:
                cache_id, cache_img = source_id, None
                if src_doc is None:
                    raise LookupError("source image record not found")
                cache_img = load_image_set([storage.path(k) for k in src_doc["file_paths"]], modality)
                if src_doc.get("mask_path"):
                    from ..imaging.loaders import load_image
                    cache_img.mask = np.rint(load_image(storage.path(src_doc["mask_path"]), modality).array).astype(np.uint8)
            if cache_img is None:
                raise RuntimeError("source could not be loaded earlier in this job")
            sample = _make_sample(ctx, job, pipeline, pcfg, src_doc, cache_img, variant, n, out_dir, expected)
            counts[{"passed": "accepted", "warning": "warnings", "rejected": "rejected"}[sample["validation_status"]]] += 1
            batch.append(sample)
        except Exception as exc:
            counts["failed"] += 1
            if len(errors) < 20:
                errors.append(f"{source_id}: {type(exc).__name__}: {exc}")
            cache_img = None if isinstance(exc, (LookupError, OSError)) else cache_img
        flush()
        if (n + 1) % 5 == 0:
            progress()
        if (n + 1) % LOG_EVERY == 0:
            _log(ctx, job_id, f"{n + 1}/{total} samples processed")
    flush(force=True)
    progress(final=True)

    produced = counts["accepted"] + counts["warnings"]
    status = "cancelled" if cancelled else ("failed" if total and produced == 0 else "completed")
    summary = {"planned": total, "generated": produced, "passed": counts["accepted"], "with_warnings": counts["warnings"],
               "rejected": counts["rejected"], "failed": counts["failed"], "errors": errors}
    _log(ctx, job_id, f"Job {status}: {produced} generated, {counts['rejected']} rejected, {counts['failed']} failed")
    store.update_one("augmentation_jobs", {"job_id": job_id}, set={
        "status": status, "completed_at": utcnow(), "summary": summary,
        "error": "All samples failed: " + "; ".join(errors[:3]) if status == "failed" else None})


def _make_sample(ctx, job, pipeline, pcfg, src_doc, src, variant, ordinal, out_dir: Path, expected) -> dict:
    job_id, seed = job["job_id"], job["seed"]
    sample_id = f"{job_id}_a{ordinal + 1:06d}"
    attempts, out, history, report = 0, None, None, None
    for attempt in range(MAX_RETRIES + 1):
        attempts = attempt + 1
        rng = np.random.default_rng(stable_entropy(seed, src_doc["image_id"], variant, attempt))
        out, history = pipeline.run(src, rng)
        report = check_output(src, out, expected_dtype=expected or src.source_dtype)
        if report["status"] != "rejected":
            break
    lineage = check_lineage(src_doc["labels"], src_doc, ("train",) if job["plan"].get("splits_defined") else ("train", None))
    if not lineage["passed"]:
        report["status"] = "rejected"
        report["messages"].append("lineage check failed (labels or split mismatch)")
    seed_record = {"job_seed": seed, "source_image_id": src_doc["image_id"], "variant": variant, "attempt": attempts - 1}
    doc = {
        "sample_id": sample_id, "job_id": job_id, "dataset_id": job["dataset_id"], "source_image_id": src_doc["image_id"],
        "patient_id": src_doc["patient_id"], "labels": list(src_doc["labels"]), "modality": job["modality"], "split": "train",
        "transform_history": history, "seed": seed_record, "attempts": attempts, "validation_status": report["status"],
        "validation": {"checks": report["checks"], "messages": report["messages"], "lineage": lineage},
        "review_status": "auto", "output_path": None, "mask_path": None, "created_at": utcnow(),
        "interpolation": pcfg.interpolation, "padding": pcfg.padding, "output_dtype": str(out.array.dtype),
        "shape": list(out.array.shape), "spacing": list(out.spacing),
    }
    if report["status"] != "rejected":
        path = save_image(out_dir / "images", sample_id, out.array, out)
        doc["output_path"], doc["format"], doc["sha256"] = ctx.storage.key(path), "nifti" if path.name.endswith(".nii.gz") else path.suffix.lstrip("."), sha256_file(path)
        if out.mask is not None:
            doc["mask_path"] = ctx.storage.key(save_image(out_dir / "masks", sample_id, out.mask.astype(np.uint8), out))
    (out_dir / "labels" / f"{sample_id}.json").write_text(json.dumps({"sample_id": sample_id, "labels": doc["labels"]}))
    (out_dir / "provenance" / f"{sample_id}.json").write_text(json.dumps(to_jsonable({k: doc[k] for k in (
        "sample_id", "job_id", "source_image_id", "patient_id", "labels", "transform_history", "seed", "attempts", "validation_status",
        "interpolation", "padding", "output_dtype", "created_at")} | {"software": job["software"]}), indent=1))
    return doc
