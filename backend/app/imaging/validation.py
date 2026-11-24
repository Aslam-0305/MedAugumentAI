"""Automated technical checks on augmented outputs (design §8).

These catch malformed or obviously unsuitable outputs. They do NOT prove clinical
validity; human review of previews remains necessary.
"""
from __future__ import annotations

import numpy as np

from .types import ImageData


def _check(name: str, ok: bool, level: str, detail: str) -> dict:
    return {"name": name, "passed": bool(ok), "level": level, "detail": detail}


def _foreground_fraction(arr: np.ndarray, ref: np.ndarray) -> float:
    lo, hi = float(ref.min()), float(ref.max())
    return float((arr > lo + 0.1 * (hi - lo)).mean()) if hi > lo else 0.0


def check_output(src: ImageData, out: ImageData, *, expected_dtype: str | None = None, range_margin: float = 0.25) -> dict:
    checks: list[dict] = []
    a, s = out.array, src.array
    checks.append(_check("shape", a.shape == s.shape, "reject", f"output {a.shape} vs source {s.shape}"))
    if expected_dtype:
        checks.append(_check("dtype", str(a.dtype) == expected_dtype, "reject", f"output {a.dtype}, expected {expected_dtype}"))
    finite = bool(np.isfinite(a).all())
    checks.append(_check("finite", finite, "reject", "NaN/Inf values present" if not finite else "all values finite"))
    if finite and a.shape == s.shape:
        span_s = float(s.max() - s.min())
        blank = float(a.max()) == float(a.min()) and span_s > 0
        checks.append(_check("not_blank", not blank, "reject", "output is constant but the source is not" if blank else "output has contrast"))
        margin = range_margin * span_s
        in_range = float(a.min()) >= float(s.min()) - margin and float(a.max()) <= float(s.max()) + margin
        checks.append(_check("intensity_range", in_range, "warning",
                             f"output range {float(a.min()):.4g}…{float(a.max()):.4g} vs source {float(s.min()):.4g}…{float(s.max()):.4g}"))
        fg_src, fg_out = _foreground_fraction(s, s), _foreground_fraction(a, s)
        if fg_src > 0.01:
            ratio = fg_out / fg_src
            checks.append(_check("content_retained_hard", ratio >= 0.3, "reject", f"foreground ratio {ratio:.2f}: most content left the field of view"))
            checks.append(_check("content_retained", ratio >= 0.6, "warning", f"foreground ratio {ratio:.2f}"))
        checks.append(_check("changed", not np.array_equal(a, s), "warning", "output is identical to the source (no effective change)"))
    geom_ok = out.spatial_shape == src.spatial_shape and np.allclose(out.spacing, src.spacing)
    if src.affine is not None:
        geom_ok = geom_ok and out.affine is not None and np.allclose(out.affine, src.affine, atol=1e-4)
    checks.append(_check("geometry", geom_ok, "reject", "spacing/orientation/shape preserved" if geom_ok else "geometry metadata changed"))
    if src.mask is not None:
        m_ok = out.mask is not None and out.mask.shape == src.spatial_shape
        checks.append(_check("mask_aligned", m_ok, "reject", "mask shape matches image" if m_ok else "mask missing or misaligned"))
        if m_ok:
            labels_ok = set(np.unique(out.mask)) <= set(np.unique(src.mask)) | {0}
            checks.append(_check("mask_labels", labels_ok, "reject", "mask labels are a subset of the source labels"))
            n_src, n_out = int((src.mask > 0).sum()), int((out.mask > 0).sum())
            if n_src:
                checks.append(_check("mask_retained_hard", n_out > 0, "reject", "annotated region left the field of view"))
                checks.append(_check("mask_retained", n_out / n_src >= 0.5, "warning", f"{n_out / n_src:.0%} of the annotated region remains"))
    failed = [c for c in checks if not c["passed"]]
    status = "rejected" if any(c["level"] == "reject" for c in failed) else "warning" if failed else "passed"
    return {"status": status, "checks": checks, "messages": [c["detail"] for c in failed]}


def check_lineage(sample_labels: list[str], source: dict, allowed_splits: tuple[str, ...] = ("train",)) -> dict:
    ok_labels = sorted(sample_labels) == sorted(source.get("labels", []))
    split = source.get("split")
    ok_split = split in allowed_splits or split is None
    return {"labels_preserved": ok_labels, "source_in_training_split": ok_split, "passed": ok_labels and ok_split}
