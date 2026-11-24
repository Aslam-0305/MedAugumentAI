"""Class-imbalance statistics (design §5)."""
from __future__ import annotations

from collections import Counter
from itertools import combinations

from ..context import AppContext
from ..utils.common import AppError
from .dataset_service import get_dataset

SCOPES = ("auto", "all", "train", "val", "test")


def valid_images(ctx: AppContext, dataset_id: str, scope: str = "all", fields: list[str] | None = None) -> list[dict]:
    flt: dict = {"dataset_id": dataset_id, "status": "valid"}
    if scope in ("train", "val", "test"):
        flt["split"] = scope
    return ctx.store.find("images", flt, sort=[("image_id", 1)], fields=fields)


def training_samples(ctx: AppContext, dataset_id: str) -> tuple[list[dict], bool]:
    """Samples eligible as augmentation sources + whether patient-level splits are defined.

    Without splits every image is treated as training data (the plan carries a leakage warning).
    """
    ds = get_dataset(ctx, dataset_id)
    if ds.get("splits_defined"):
        return valid_images(ctx, dataset_id, "train", ["image_id", "labels", "patient_id", "split", "size_bytes"]), True
    return valid_images(ctx, dataset_id, "all", ["image_id", "labels", "patient_id", "split", "size_bytes"]), False


def dataset_statistics(ctx: AppContext, dataset_id: str, scope: str = "auto") -> dict:
    if scope not in SCOPES:
        raise AppError(f"scope must be one of {SCOPES}", 400, "invalid_request")
    ds = get_dataset(ctx, dataset_id)
    defined = bool(ds.get("splits_defined"))
    if scope == "auto":
        scope = "train" if defined else "all"
    if scope != "all" and not defined:
        raise AppError("No splits exist yet; create or register patient-level splits first", 409, "no_splits")
    imgs = valid_images(ctx, dataset_id, scope, ["image_id", "labels", "patient_id", "split"])
    n = len(imgs)
    counts: Counter = Counter()
    pairs: Counter = Counter()
    for im in imgs:
        counts.update(im["labels"])
        for a, b in combinations(sorted(im["labels"]), 2):
            pairs[(a, b)] += 1
    classes = ds["classes"]
    total_labels = sum(counts.values()) or 1
    rows = [{"label": c, "count": counts.get(c, 0), "percent_of_images": round(100 * counts.get(c, 0) / n, 2) if n else 0.0,
             "percent_of_labels": round(100 * counts.get(c, 0) / total_labels, 2)} for c in classes]
    nonzero = [r["count"] for r in rows if r["count"] > 0]
    per_split: dict[str, dict] = {}
    if defined:
        for sp in ("train", "val", "test"):
            part = valid_images(ctx, dataset_id, sp, ["labels", "patient_id"])
            c = Counter(l for im in part for l in im["labels"])
            per_split[sp] = {"images": len(part), "patients": len({im["patient_id"] for im in part}), "classes": {k: c.get(k, 0) for k in classes}}
    matrix = [[(counts.get(a, 0) if a == b else pairs.get((min(a, b), max(a, b)), 0)) for b in classes] for a in classes]
    return {
        "dataset_id": dataset_id, "scope": scope, "splits_defined": defined, "annotation_type": ds["annotation_type"],
        "n_images": n, "n_patients": len({im["patient_id"] for im in imgs}), "classes": rows,
        "largest_class": max(rows, key=lambda r: r["count"])["label"] if rows and nonzero else None,
        "smallest_class": min((r for r in rows if r["count"] > 0), key=lambda r: r["count"])["label"] if nonzero else None,
        "imbalance_ratio": round(max(nonzero) / min(nonzero), 2) if nonzero else None,
        "empty_classes": [r["label"] for r in rows if r["count"] == 0],
        "label_cardinality": round(sum(len(im["labels"]) for im in imgs) / n, 3) if n else 0,
        "cooccurrence": {"labels": classes, "matrix": matrix} if ds["annotation_type"] == "multilabel" else None,
        "splits": per_split,
    }
