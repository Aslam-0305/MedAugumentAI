"""Self-describing dataset export (design §14).

Package layout inside the ZIP:
  train/images|masks/   originals (optional) + accepted augmented samples
  val/images, test/images   untouched originals (optional)
  manifest.csv / manifest.json   one row per file, labels, lineage, transform history, sha256
  provenance.jsonl, config.json, summary_report.json / .md, README.txt
File names are generated from ids, never from the uploaded file names (which may contain identifiers).
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from ..context import AppContext
from ..imaging.loaders import load_image_set, save_image
from ..utils.common import AppError, new_id, not_found, sha256_file, to_jsonable, utcnow
from .dataset_service import get_dataset
from .job_service import get_job

COPYABLE = {"png", "jpeg", "tiff", "nifti", "jpg"}
README = """MedAugment AI export
====================
Research data-preparation output. NOT a diagnostic product.
* Augmented files are transformed copies of existing training images. They are not new patients or new clinical observations.
* Validation/test images (if included) are original, unmodified files from the source dataset.
* manifest.csv lists every file with its labels, source image, pseudonymous subject id and transformation history.
* Subject ids are pseudonymised; DICOM metadata is not exported (DICOM inputs are converted to NIfTI/PNG).
* Technical checks do not prove clinical validity: review samples before using them.
"""


def public_export(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("archive_path",)}


def get_export(ctx: AppContext, export_id: str) -> dict:
    doc = ctx.store.find_one("exports", {"export_id": export_id})
    if not doc:
        raise not_found("Export", export_id)
    return doc


def list_exports(ctx: AppContext, dataset_id: str | None = None) -> list[dict]:
    return [public_export(e) for e in ctx.store.find("exports", {"dataset_id": dataset_id} if dataset_id else None, sort=[("created_at", -1)])]


def create_export(ctx: AppContext, job_id: str, *, include_originals: bool = True, include_validation_test: bool = True,
                  include_warnings: bool = True) -> dict:
    job = get_job(ctx, job_id)
    if job["status"] != "completed":
        raise AppError("Only completed jobs can be exported", 409, "conflict")
    eid = new_id("exp")
    doc = {"export_id": eid, "dataset_id": job["dataset_id"], "job_id": job_id, "status": "queued", "created_at": utcnow(),
           "completed_at": None, "options": {"include_originals": include_originals, "include_validation_test": include_validation_test,
                                             "include_warnings": include_warnings},
           "archive_path": None, "manifest_path": None, "size_bytes": None, "n_files": None, "error": None, "report": None}
    ctx.store.insert_one("exports", doc)
    ctx.executor.submit(run_export, ctx, eid)
    return public_export(doc)


def run_export(ctx: AppContext, export_id: str) -> None:
    doc = get_export(ctx, export_id)
    ctx.store.update_one("exports", {"export_id": export_id}, set={"status": "running"})
    try:
        result = _build(ctx, doc)
        ctx.store.update_one("exports", {"export_id": export_id}, set={"status": "completed", "completed_at": utcnow(), **result})
    except Exception as exc:
        shutil.rmtree(ctx.storage.export_dir(export_id), ignore_errors=True)
        ctx.store.update_one("exports", {"export_id": export_id},
                             set={"status": "failed", "completed_at": utcnow(), "error": f"{type(exc).__name__}: {exc}"})


def _copy_original(ctx, im: dict, dest_dir: Path, stem: str) -> Path:
    files = [ctx.storage.path(k) for k in im["file_paths"]]
    if len(files) == 1 and files[0].is_file() and im["format"] in COPYABLE:
        suffix = ".nii.gz" if files[0].name.endswith(".nii.gz") else files[0].suffix.lower()
        dest = dest_dir / f"{stem}{suffix}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(files[0], dest)  # byte-for-byte: originals stay unchanged
        return dest
    img = load_image_set(files, im["modality"])  # DICOM / multi-file sequences are converted (drops DICOM metadata)
    return save_image(dest_dir, stem, img.array, img)


def _build(ctx: AppContext, exp: dict) -> dict:
    opts = exp["options"]
    job = get_job(ctx, exp["job_id"], full=True)
    ds = get_dataset(ctx, exp["dataset_id"])
    classes = ds["classes"]
    root_name = f"medaugment_export_{exp['export_id']}"
    out_dir = ctx.storage.export_dir(exp["export_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{root_name}.zip"
    rows: list[dict] = []

    def add_row(zf, src: Path, rel: str, **meta) -> None:
        zf.write(src, f"{root_name}/{rel}", compress_type=zipfile.ZIP_STORED)
        rows.append({"file_path": rel, "labels": "|".join(meta["labels"]), **{c: int(c in meta["labels"]) for c in classes},
                     "sha256": sha256_file(src), **{k: v for k, v in meta.items() if k != "labels"}})

    samples = ctx.store.find("augmented_samples", {"job_id": exp["job_id"]}, sort=[("sample_id", 1)])
    ok_status = ("passed", "warning") if opts["include_warnings"] else ("passed",)
    accepted = [s for s in samples if s["validation_status"] in ok_status and s["review_status"] != "rejected" and s.get("output_path")]
    excluded = len(samples) - len(accepted)
    tmp = ctx.storage.tmp_dir() / exp["export_id"]
    tmp.mkdir(parents=True, exist_ok=True)
    train_orig = ctx.store.find("images", {"dataset_id": ds["dataset_id"], "status": "valid"} | ({"split": "train"} if ds["splits_defined"] else {}), sort=[("image_id", 1)])
    exported_orig = Counter()
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if opts["include_originals"]:
                for im in train_orig:
                    p = _copy_original(ctx, im, tmp / "o", im["image_id"])
                    add_row(zf, p, f"train/images/{p.name}", labels=im["labels"], split="train", is_augmented=0, image_id=im["image_id"],
                            source_image_id="", patient_id=im["patient_id"], job_id="", transform_history="", validation_status="")
                    exported_orig.update(im["labels"])
                    if im.get("mask_path"):
                        mp = ctx.storage.path(im["mask_path"])
                        zf.write(mp, f"{root_name}/train/masks/{im['image_id']}{'.nii.gz' if mp.name.endswith('.nii.gz') else mp.suffix}")
            for s in accepted:
                p = ctx.storage.path(s["output_path"])
                add_row(zf, p, f"train/images/{p.name}", labels=s["labels"], split="train", is_augmented=1, image_id=s["sample_id"],
                        source_image_id=s["source_image_id"], patient_id=s["patient_id"], job_id=s["job_id"],
                        transform_history=json.dumps(to_jsonable([{"name": h["name"], "sampled": h["sampled"]} for h in s["transform_history"]])),
                        validation_status=s["validation_status"])
                if s.get("mask_path"):
                    mp = ctx.storage.path(s["mask_path"])
                    zf.write(mp, f"{root_name}/train/masks/{mp.name}")
            if opts["include_validation_test"] and ds["splits_defined"]:
                for sp in ("val", "test"):
                    for im in ctx.store.find("images", {"dataset_id": ds["dataset_id"], "status": "valid", "split": sp}, sort=[("image_id", 1)]):
                        p = _copy_original(ctx, im, tmp / sp, im["image_id"])
                        add_row(zf, p, f"{sp}/images/{p.name}", labels=im["labels"], split=sp, is_augmented=0, image_id=im["image_id"],
                                source_image_id="", patient_id=im["patient_id"], job_id="", transform_history="", validation_status="")
            fields = ["file_path", "split", "is_augmented", "image_id", "source_image_id", "patient_id", "job_id", "labels", *classes,
                      "validation_status", "transform_history", "sha256"]
            sio = io.StringIO()
            w = csv.DictWriter(sio, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
            gen = Counter(l for s in accepted for l in s["labels"])
            report = {
                "export_id": exp["export_id"], "job_id": job["job_id"], "dataset_id": ds["dataset_id"], "created_at": utcnow(),
                "options": opts, "annotation_type": ds["annotation_type"],
                "before_counts_train": {c["label"]: c["original"] for c in job["plan"]["classes"]},
                "requested_targets": {c["label"]: c["target"] for c in job["plan"]["classes"]},
                "generated_counts": {c: gen.get(c, 0) for c in classes},
                "final_counts_train": {c: (exported_orig.get(c, 0) if opts["include_originals"] else 0) + gen.get(c, 0) for c in classes},
                "samples": {"planned": job["progress"]["total"], "exported": len(accepted), "rejected_by_checks": sum(s["validation_status"] == "rejected" for s in samples),
                            "rejected_by_user": sum(s["review_status"] == "rejected" for s in samples), "excluded_total": excluded},
                "plan_warnings": job["plan"]["warnings"], "files": len(rows),
                "disclaimer": "Augmented samples are transformed copies of existing training images, not new patients or independent clinical observations.",
            }
            md = [f"# Export summary {exp['export_id']}", "", f"Job `{job['job_id']}` on dataset **{ds['name']}** ({ds['modality'].upper()}).", "",
                  "| Class | Before (train) | Requested target | Generated & exported | Final (exported train) |", "|---|---|---|---|---|"]
            md += [f"| {c} | {report['before_counts_train'].get(c, 0)} | {report['requested_targets'].get(c, '')} | {report['generated_counts'][c]} | {report['final_counts_train'][c]} |" for c in classes]
            md += ["", f"Exported {len(accepted)} of {report['samples']['planned']} planned samples; {report['samples']['rejected_by_checks']} rejected by checks, "
                       f"{report['samples']['rejected_by_user']} rejected by reviewer.", "", report["disclaimer"]]
            for name, data in {
                "manifest.csv": sio.getvalue(), "manifest.json": json.dumps(to_jsonable(rows), indent=1),
                "provenance.jsonl": "\n".join(json.dumps(to_jsonable({k: s[k] for k in ("sample_id", "source_image_id", "patient_id", "labels", "transform_history", "seed", "attempts", "validation_status", "review_status", "interpolation", "padding", "output_dtype")})) for s in accepted),
                "config.json": json.dumps(to_jsonable({"seed": job["seed"], "config": job["config"], "software": job["software"]}), indent=1),
                "summary_report.json": json.dumps(to_jsonable(report), indent=1), "summary_report.md": "\n".join(md), "README.txt": README,
            }.items():
                zf.writestr(f"{root_name}/{name}", data)
        (out_dir / "manifest.csv").write_text(sio.getvalue())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"archive_path": ctx.storage.key(zip_path), "manifest_path": ctx.storage.key(out_dir / "manifest.csv"),
            "size_bytes": zip_path.stat().st_size, "n_files": len(rows), "report": to_jsonable(report)}
