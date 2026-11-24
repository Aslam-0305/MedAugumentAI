"""Intensity, noise, blur and occlusion transforms. Operate on one channel (float32)."""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


def brightness_contrast(x, p, rng, ctx):
    span = float(x.max() - x.min()) or 1.0
    c = float(rng.uniform(1 - p["contrast"], 1 + p["contrast"]))
    b = float(rng.uniform(-p["brightness"], p["brightness"])) * span
    m = float(x.mean())
    return (x - m) * c + m + b, {"contrast": c, "brightness_abs": b}


def gamma(x, p, rng, ctx):
    lo, hi = p["gamma_range"]
    g = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
    mn, span = float(x.min()), float(x.max() - x.min())
    if span <= 0:
        return x, {"gamma": g, "skipped": True}
    return np.power((x - mn) / span, g) * span + mn, {"gamma": g}


def hu_shift(x, p, rng, ctx):
    s = float(rng.uniform(-p["max_shift_hu"], p["max_shift_hu"]))
    return x + s, {"shift_hu": s}


def intensity_scale(x, p, rng, ctx):
    f = float(rng.uniform(1 - p["max_scale_delta"], 1 + p["max_scale_delta"]))
    return x * f, {"factor": f}


def bias_field(x, p, rng, ctx):
    s = p["strength"]
    low = rng.uniform(1 - s, 1 + s, size=(4,) * x.ndim).astype(np.float32)
    field = ndi.zoom(low, [d / 4 for d in x.shape], order=3, mode="nearest")
    if field.shape != x.shape:
        field = field[tuple(slice(0, d) for d in x.shape)]
        field = np.pad(field, [(0, d - f) for d, f in zip(x.shape, field.shape)], mode="edge")
    return x * field, {"strength": float(s), "field_min": float(field.min()), "field_max": float(field.max())}


def gaussian_noise(x, p, rng, ctx):
    level = float(rng.uniform(0, p["max_sigma"]))
    if ctx["modality"] == "ct":
        sigma, unit = level, "hu"
    else:
        sigma, unit = level * float(x.std()), "fraction_of_std"
    if ctx["modality"] == "mri" and float(x.min()) >= 0 and sigma > 0:
        n1, n2 = rng.normal(0, sigma, x.shape), rng.normal(0, sigma, x.shape)
        return np.sqrt((x + n1) ** 2 + n2**2).astype(np.float32), {"level": level, "unit": unit, "rician": True}
    return x + rng.normal(0, sigma, x.shape).astype(np.float32), {"level": level, "unit": unit, "rician": False}


def gaussian_blur(x, p, rng, ctx):
    sigma = float(rng.uniform(0, p["max_sigma"]))
    if sigma <= 0.05:
        return x, {"sigma_voxels": sigma, "skipped": True}
    sp = np.asarray(ctx["spacing"], dtype=float)
    per_axis = sigma * sp.min() / sp  # same physical blur in every direction
    return ndi.gaussian_filter(x, per_axis, mode="nearest"), {"sigma_voxels": sigma}


def sample_erasing_box(p, rng, shape, mask) -> dict:
    nd = len(shape)
    total = float(np.prod(shape))
    for _ in range(10):
        area = float(rng.uniform(0.2 * p["max_area"], p["max_area"]))
        aspect = np.exp(rng.uniform(-0.3, 0.3, nd))
        aspect /= np.prod(aspect) ** (1 / nd)
        size = np.maximum(1, np.minimum((area * total) ** (1 / nd) * aspect, np.asarray(shape) - 1)).astype(int)
        start = np.array([int(rng.integers(0, s - z + 1)) for s, z in zip(shape, size)])
        sl = tuple(slice(a, a + z) for a, z in zip(start, size))
        if mask is None or not np.any(mask[sl] > 0):
            return {"slices": [[int(s.start), int(s.stop)] for s in sl], "area_fraction": float(np.prod(size) / total)}
    return {"skipped": True, "reason": "could not place a patch outside the annotated mask"}


def apply_erasing_box(x, box: dict):
    if box.get("skipped"):
        return x
    out = x.copy()
    out[tuple(slice(a, b) for a, b in box["slices"])] = float(x.mean())
    return out


INTENSITY_FUNCS = {
    "brightness_contrast": brightness_contrast, "gamma": gamma, "hu_shift": hu_shift,
    "intensity_scale": intensity_scale, "bias_field": bias_field,
    "gaussian_noise": gaussian_noise, "gaussian_blur": gaussian_blur,
}
