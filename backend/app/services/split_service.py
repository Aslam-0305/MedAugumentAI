"""Patient-level data splits (design §6). Splits are made BEFORE augmentation and only train is augmented."""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from ..context import AppContext
from ..utils.common import AppError, stable_entropy, utcnow
from .analysis_service import valid_images
from .dataset_service import get_dataset

NAMES = ("train", "val", "test")


def create_splits(ctx: AppContext, dataset_id: str, *, mode: str = "create", ratios: dict | None = None, seed: int = 42) -> dict:
    ds = get_dataset(ctx, dataset_id)
    if ds["status"] == "failed":
        raise AppError("This dataset has no valid images", 409, "dataset_failed")
    if ctx.store.count("augmentation_jobs", {"dataset_id": dataset_id}):
        raise AppError("Splits cannot change after augmentation jobs exist; delete the jobs or create a new dataset", 409, "conflict")
    imgs = valid_images(ctx, dataset_id, "all", ["image_id", "labels", "patient_id", "source_split"])
    if mode == "use_existing":
        assignment = _existing(imgs)
        info = {"mode": "use_existing", "seed": None}
    elif mode == "create":
        r = {k: float((ratios or {}).get(k, d)) for k, d in zip(NAMES, (0.7, 0.15, 0.15))}
        if any(v < 0 for v in r.values()) or abs(sum(r.values()) - 1.0) > 1e-6 or r["train"] <= 0:
            raise AppError("Split ratios must be non-negative, sum to 1, and train must be > 0", 400, "invalid_config")
        assignment = _stratified_patient_split(imgs, r, seed)
        info = {"mode": "create", "seed": seed, "ratios": r}
    else:
        raise AppError("mode must be 'create' or 'use_existing'", 400, "invalid_request")
    for sp in NAMES:
        ids = [i for i, s in assignment.items() if s == sp]
        for k in range(0, len(ids), 500):
            ctx.store.update_many("images", {"dataset_id": dataset_id, "image_id": {"$in": ids[k : k + 500]}}, set={"split": sp})
    summary = _summarise(imgs, assignment, ds["classes"])
    info.update({"created_at": utcnow(), "warnings": summary["warnings"]})
    ctx.store.update_one("datasets", {"dataset_id": dataset_id}, set={"splits_defined": True, "split_info": info})
    return {"dataset_id": dataset_id, **info, "summary": summary["table"]}


def _existing(imgs: list[dict]) -> dict[str, str]:
    missing = [i["image_id"] for i in imgs if i.get("source_split") not in NAMES]
    if missing:
        raise AppError(f"{len(missing)} image(s) have no train/val/test value in the manifest 'split' column", 400, "missing_split")
    per_patient: dict[str, set] = defaultdict(set)
    for i in imgs:
        per_patient[i["patient_id"]].add(i["source_split"])
    bad = [p for p, s in per_patient.items() if len(s) > 1]
    if bad:
        raise AppError(f"{len(bad)} patient(s) span several splits in the supplied manifest (data leakage)", 400, "patient_split_conflict")
    return {i["image_id"]: i["source_split"] for i in imgs}


def _stratified_patient_split(imgs: list[dict], ratios: dict[str, float], seed: int) -> dict[str, str]:
    rng = np.random.default_rng(stable_entropy("split", seed))
    patients: dict[str, list[dict]] = defaultdict(list)
    for im in imgs:
        patients[im["patient_id"]].append(im)
    label_total = Counter(l for im in imgs for l in im["labels"])
    n_total = len(imgs)
    names = [n for n in NAMES if ratios[n] > 0]
    label_cnt = {n: Counter() for n in names}
    img_cnt = {n: 0 for n in names}
    # rare-label patients first so scarce classes are spread over the splits
    order = list(patients)
    rng.shuffle(order)
    order.sort(key=lambda p: min(label_total[l] for im in patients[p] for l in im["labels"]))
    out: dict[str, str] = {}
    for p in order:
        plabels = Counter(l for im in patients[p] for l in im["labels"])

        def score(n: str) -> float:
            lab = sum((ratios[n] * label_total[l] - label_cnt[n][l]) / max(label_total[l], 1) for l in plabels)
            return lab + (ratios[n] * n_total - img_cnt[n]) / max(n_total, 1)

        best = max(names, key=score)
        for im in patients[p]:
            out[im["image_id"]] = best
        label_cnt[best].update(plabels)
        img_cnt[best] += len(patients[p])
    return out


def _summarise(imgs: list[dict], assignment: dict[str, str], classes: list[str]) -> dict:
    table = {n: {"images": 0, "classes": Counter()} for n in NAMES}
    for im in imgs:
        t = table[assignment[im["image_id"]]]
        t["images"] += 1
        t["classes"].update(im["labels"])
    warnings = []
    for n in ("val", "test"):
        if table[n]["images"]:
            absent = [c for c in classes if table[n]["classes"].get(c, 0) == 0]
            if absent:
                warnings.append(f"Split '{n}' contains no examples of: {', '.join(absent)}")
    return {"table": {n: {"images": t["images"], "classes": {c: t["classes"].get(c, 0) for c in classes}} for n, t in table.items()},
            "warnings": warnings}
