"""Dataset creation, validation and queries (design §4, §9 steps 1-4)."""
from __future__ import annotations

import concurrent.futures
import os
import secrets
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ..context import AppContext
from ..imaging.adapters import get_adapter
from ..imaging.loaders import load_image, load_image_set
from ..imaging.metadata import pseudonymize
from ..imaging.types import ImageLoadError, MissingDependencyError, orientation_codes
from ..utils.common import AppError, new_id, not_found, sha256_file, utcnow
from . import ingestion
from .ingestion import FileIndex, Parsed, issue

LAYOUTS = ("manifest", "folders")
MAX_STORED_ISSUES = 500


def public_dataset(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "pseudonym_salt"}


def get_dataset(ctx: AppContext, dataset_id: str) -> dict:
    doc = ctx.store.find_one("datasets", {"dataset_id": dataset_id})
    if not doc:
        raise not_found("Dataset", dataset_id)
    return doc


def list_datasets(ctx: AppContext) -> list[dict]:
    return [public_dataset(d) for d in ctx.store.find("datasets", sort=[("created_at", -1)])]


def _find_manifests(root: Path) -> list[Path]:
    manifest_exts = {".csv", ".xlsx", ".xls"}
    candidates = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in manifest_exts and len(p.relative_to(root).parts) <= 3
        and not p.name.startswith("._") and not p.name.startswith("~$") and p.name.lower() not in ingestion.JUNK
    ]
    if not candidates:
        return []
    # If an explicit single master manifest exists, use that directly
    master_manifests = [p for p in candidates if p.name.lower() in ("manifest.csv", "manifest.xlsx", "dataset.csv", "dataset.xlsx")]
    if master_manifests:
        csvs = [p for p in master_manifests if p.suffix.lower() == ".csv"]
        return [csvs[0]] if csvs else [master_manifests[0]]
    return sorted(candidates, key=lambda p: (len(p.parts), p.name.lower()))


def _find_manifest(root: Path) -> Path | None:
    found = _find_manifests(root)
    return found[0] if len(found) == 1 else None


def create_dataset(ctx: AppContext, *, name: str, modality: str, layout: str, archives: list[Path],
                   loose_files: list[tuple[str, Path]], manifest: Path | None) -> dict:
    name = (name or "").strip()
    if not name:
        raise AppError("A dataset name is required", 400, "invalid_request")
    if layout not in LAYOUTS:
        raise AppError(f"layout must be one of {LAYOUTS}", 400, "invalid_request")
    adapter = get_adapter(modality)
    if not archives and not loose_files:
        raise AppError("Upload a ZIP archive (or image files) with the dataset", 400, "invalid_request")

    dataset_id = new_id("ds")
    storage = ctx.storage
    original = storage.original_dir(dataset_id)
    original.mkdir(parents=True)
    storage.manifests_dir(dataset_id).mkdir(parents=True)
    storage.metadata_dir(dataset_id).mkdir(parents=True)
    try:
        for arc in archives:
            ingestion.safe_extract_zip(arc, original, ctx.settings)
        for filename, tmp in loose_files:
            dest = original / ingestion.sanitize_relpath(filename)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp), dest)
        index = FileIndex(original)
        if layout == "manifest":
            manifest_files = [manifest] if manifest else _find_manifests(original)
            if not manifest_files:
                raise AppError("Manifest layout needs a CSV or Excel manifest (upload it separately or include it in the archive)", 400, "bad_manifest")
            parsed, unified_csv = ingestion.parse_manifests(manifest_files)
            (storage.manifests_dir(dataset_id) / "manifest.csv").write_text(unified_csv, encoding="utf-8")
        else:
            parsed = ingestion.parse_folders(original, index)
        doc, images = _validate_and_build(ctx, dataset_id, name, modality, layout, parsed, index, adapter)
    except Exception:
        shutil.rmtree(storage.dataset_dir(dataset_id), ignore_errors=True)
        raise
    ctx.store.insert_one("datasets", doc)
    ctx.store.insert_many("images", images)
    return public_dataset(doc)


def _validate_and_build(ctx, dataset_id, name, modality, layout, parsed: Parsed, index: FileIndex, adapter):
    storage = ctx.storage
    salt = secrets.token_hex(16)
    issues = list(parsed.issues)
    seen_paths: dict[str, int] = {}
    seen_hash: dict[str, str] = {}
    phi: Counter = Counter()
    patient_splits: dict[str, set] = defaultdict(set)
    has_patient_col = any(r.raw_patient for r in parsed.records)
    if not has_patient_col:
        issues.append(issue("warning", "no_patient_id", "No patient/subject IDs were provided: every image is treated as its own subject, so a patient-level split cannot prevent leakage between images of the same patient."))

    # Pass 1: Quick preliminary checks (missing paths, labels, duplicate paths, missing files)
    preliminary_records = []
    to_load = []

    for n, rec in enumerate(parsed.records, start=1):
        image_id = f"{dataset_id}_i{n:06d}"
        ref = f"row {rec.row}" if layout == "manifest" else (rec.paths[0] if rec.paths else f"item {n}")
        local: list[dict] = []
        doc = {
            "image_id": image_id, "dataset_id": dataset_id, "modality": modality, "labels": sorted(set(rec.labels)),
            "source_split": rec.split, "split": None, "status": "invalid", "created_at": utcnow(), "source_ref": ref
        }
        raw = rec.raw_patient or f"__image__{image_id}"
        doc["patient_id"] = pseudonymize(salt, raw)

        if not rec.paths:
            local.append(issue("error", "missing_path", "No image path given", ref))
        if not doc["labels"]:
            local.append(issue("error", "missing_label", "Image has no label (all-zero or empty label cells)", ref))

        key = "|".join(rec.paths)
        if key in seen_paths and rec.paths:
            local.append(issue("error", "duplicate_path", f"Path repeated (first used in row {seen_paths[key]})", ref))
        seen_paths.setdefault(key, rec.row)

        paths = rec.resolved or [index.resolve(p) for p in rec.paths]
        if rec.paths and any(p is None for p in paths):
            missing = [rp for rp, p in zip(rec.paths, paths) if p is None]
            local.append(issue("error", "missing_file", f"File not found in the upload: {missing[0]}", ref))

        has_error = any(i["level"] == "error" for i in local)
        preliminary_records.append((n, rec, doc, local, paths, has_error))
        if not has_error:
            to_load.append((n, rec, ref, paths))

    # Pass 2: Heavy image decoding, adapter validation, and hashing across thread pool
    def _load_and_validate(item):
        n, rec, ref, paths = item
        load_issues = []
        phi_tags = []
        image_data = None
        digest = None
        try:
            if modality != "mri" and len(paths) > 1:
                load_issues.append(issue("error", "multiple_paths", "Several paths per row are only supported for MRI sequences", ref))
            else:
                img = load_image_set(paths, modality)
                mask_note = _attach_mask(rec, img, index, modality, load_issues, ref, storage)
                for it in adapter.validate_input(img):
                    load_issues.append({**it, "ref": ref})
                for t in img.meta.get("phi_tags", []):
                    phi_tags.append(t)
                safe = {k: v for k, v in img.meta.items() if k != "phi_tags"}
                if not any(i["level"] == "error" for i in load_issues):
                    files = [p for p in paths if p.is_file()]
                    digest = "-".join(sha256_file(p) for p in files)[:128] if files and len(files) == len(paths) else None
                    image_data = {
                        "status": "valid", "format": img.fmt, "file_paths": [storage.key(p) for p in paths], "file_path": storage.key(paths[0]),
                        "mask_path": mask_note, "dimensions": list(img.array.shape), "n_channels": img.n_channels,
                        "spatial_ndim": img.spatial_ndim, "spacing": list(img.spacing), "orientation": orientation_codes(img.affine),
                        "dtype": img.source_dtype, "intensity_range": [float(img.array.min()), float(img.array.max())],
                        "sha256": digest, "metadata": safe,
                        "size_bytes": int(sum(f.stat().st_size for f in files)) if files else int(img.array.nbytes),
                    }
        except ImageLoadError as exc:
            load_issues.append(issue("error", "unreadable", f"Cannot read image: {exc}", ref))
        except MissingDependencyError as exc:
            load_issues.append(issue("error", "missing_dependency", str(exc), ref))
        except Exception as exc:
            load_issues.append(issue("error", "unreadable", f"Unexpected error reading image: {type(exc).__name__}: {exc}", ref))
        return n, load_issues, phi_tags, image_data, digest

    load_results = {}
    if to_load:
        worker_count = min(8, os.cpu_count() or 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
            for n, load_issues, phi_tags, image_data, digest in pool.map(_load_and_validate, to_load):
                load_results[n] = (load_issues, phi_tags, image_data, digest)

    # Pass 3: Assemble docs, apply duplicate digest checks, and collect issues
    images: list[dict] = []
    for n, rec, doc, local, paths, has_prelim_error in preliminary_records:
        ref = doc["source_ref"]
        if not has_prelim_error and n in load_results:
            load_issues, phi_tags, image_data, digest = load_results[n]
            local.extend(load_issues)
            for t in phi_tags:
                phi[t] += 1
            if image_data:
                doc.update(image_data)
            if digest:
                if digest in seen_hash:
                    dup_warn = issue("warning", "duplicate_content", f"Identical file content to {seen_hash[digest]}: duplicates can leak across splits", ref)
                    local.append(dup_warn)
                else:
                    seen_hash[digest] = doc["image_id"]

        doc["issues"] = local
        if doc["status"] == "valid" and any(i["level"] == "error" for i in local):
            doc["status"] = "invalid"
        issues += local
        images.append(doc)

    if phi:
        issues.append(issue("warning", "phi_detected", f"DICOM files contain direct identifiers ({', '.join(sorted(phi))}). MedAugment AI never stores, logs or exports them; subject IDs are pseudonymised. Prefer de-identified data."))
    for doc in images:
        if doc["status"] == "valid" and doc["source_split"]:
            patient_splits[doc["patient_id"]].add(doc["source_split"])
    conflicts = [p for p, s in patient_splits.items() if len(s) > 1]
    if conflicts:
        issues.append(issue("error", "patient_split_conflict", f"{len(conflicts)} patient(s) appear in more than one supplied split (leakage). Fix the manifest before using the supplied splits."))

    valid = [d for d in images if d["status"] == "valid"]
    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]
    classes = sorted({l for d in valid for l in d["labels"]})
    if not valid:
        status = "failed"
    elif any(d["status"] == "invalid" for d in images) or conflicts:
        status = "ready_with_issues"
    else:
        status = "ready"
    single = all(len(d["labels"]) == 1 for d in valid)
    annotation_type = "single" if (single and parsed.annotation_type == "single") else "multilabel"
    ctr = Counter(i["code"] for i in issues)
    doc = {
        "dataset_id": dataset_id, "name": name, "modality": modality, "layout": layout, "annotation_type": annotation_type,
        "classes": classes, "status": status, "created_at": utcnow(), "storage_root": storage.key(storage.dataset_dir(dataset_id)),
        "pseudonym_salt": salt, "splits_defined": False, "split_info": None,
        "counts": {"total": len(images), "valid": len(valid), "invalid": len(images) - len(valid), "patients": len({d["patient_id"] for d in valid})},
        "validation": {"errors": len(errors), "warnings": len(warnings), "by_code": dict(ctr),
                       "issues": [i for i in issues if i["level"] == "error"][:MAX_STORED_ISSUES // 2] + warnings[:MAX_STORED_ISSUES // 2],
                       "truncated": len(issues) > MAX_STORED_ISSUES},
        "has_supplied_splits": any(d["source_split"] for d in valid),
    }
    return doc, images


def _attach_mask(rec, img, index, modality, local, ref, storage) -> str | None:
    """Load the optional mask for a record; returns its storage key (or None) and sets img.mask."""
    if not rec.mask:
        return None
    mp = index.resolve(rec.mask)
    if mp is None:
        local.append(issue("error", "missing_mask", f"Mask file not found: {rec.mask}", ref))
        return None
    m = load_image(mp, modality)
    if m.has_channels or m.spatial_shape != img.spatial_shape:
        local.append(issue("error", "mask_shape_mismatch", f"Mask shape {m.array.shape} does not match image spatial shape {img.spatial_shape}", ref))
        return None
    img.mask = np.rint(m.array).astype(np.uint8)
    return storage.key(mp)


def delete_dataset(ctx: AppContext, dataset_id: str) -> None:
    get_dataset(ctx, dataset_id)
    if ctx.store.count("augmentation_jobs", {"dataset_id": dataset_id, "status": {"$in": ["queued", "running"]}}):
        raise AppError("Cancel running jobs before deleting the dataset", 409, "conflict")
    jobs = ctx.store.find("augmentation_jobs", {"dataset_id": dataset_id}, fields=["job_id"])
    for j in jobs:
        shutil.rmtree(ctx.storage.augmented_dir(j["job_id"]), ignore_errors=True)
        ctx.store.delete_many("augmented_samples", {"job_id": j["job_id"]})
    for e in ctx.store.find("exports", {"dataset_id": dataset_id}, fields=["export_id"]):
        shutil.rmtree(ctx.storage.export_dir(e["export_id"]), ignore_errors=True)
    for coll in ("exports", "augmentation_jobs", "images"):
        ctx.store.delete_many(coll, {"dataset_id": dataset_id})
    ctx.store.delete_many("datasets", {"dataset_id": dataset_id})
    shutil.rmtree(ctx.storage.dataset_dir(dataset_id), ignore_errors=True)


def list_images(ctx: AppContext, dataset_id: str, *, split: str | None = None, label: str | None = None,
                status: str | None = None, skip: int = 0, limit: int = 48) -> dict:
    get_dataset(ctx, dataset_id)
    flt: dict = {"dataset_id": dataset_id}
    if split:
        flt["split"] = split
    if label:
        flt["labels"] = label
    if status:
        flt["status"] = status
    total = ctx.store.count("images", flt)
    items = ctx.store.find("images", flt, sort=[("image_id", 1)], skip=skip, limit=min(limit, 500))
    keep = ("image_id", "dataset_id", "patient_id", "labels", "split", "source_split", "status", "format", "dimensions", "spacing",
            "orientation", "modality", "issues", "dtype", "n_channels", "spatial_ndim", "intensity_range", "metadata")
    return {"total": total, "items": [{k: v for k, v in d.items() if k in keep} for d in items]}
