"""PNG previews for originals and augmented samples (display only; never alters stored data)."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from ..context import AppContext
from ..imaging.loaders import load_image_set
from ..imaging.types import ImageData
from ..utils.common import AppError, not_found

CT_WINDOWS = {"soft": (40, 400), "lung": (-600, 1500), "bone": (400, 1800)}


def render_array(img: ImageData, *, channel: int = 0, slice_index: int | None = None, axis: int = 2,
                 modality: str | None = None, window: str | None = None, max_size: int = 512) -> bytes:
    arr = img.array
    if img.has_channels:
        arr = arr[min(max(channel, 0), arr.shape[0] - 1)]
    if img.spatial_ndim == 3:
        axis = min(max(axis, 0), 2)
        idx = arr.shape[axis] // 2 if slice_index is None else min(max(slice_index, 0), arr.shape[axis] - 1)
        arr = np.flipud(np.take(arr, idx, axis=axis).T)  # rows = second axis, origin at the bottom (radiological-style)
    arr = arr.astype(np.float32)
    modality = modality or img.modality
    if modality == "ct" and window != "auto":
        c, w = CT_WINDOWS.get(window or "soft", CT_WINDOWS["soft"])
        lo, hi = c - w / 2, c + w / 2
    else:
        lo, hi = np.percentile(arr, [1, 99])
        if hi <= lo:
            lo, hi = float(arr.min()), float(arr.max()) or 1.0
    out = (np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)
    im = Image.fromarray(out)
    im.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def render_record(ctx: AppContext, record_id: str, *, channel: int = 0, slice_index: int | None = None,
                  axis: int = 2, window: str | None = None, max_size: int = 512) -> bytes:
    """`record_id` is either an original image id or an augmented sample id."""
    doc = ctx.store.find_one("images", {"image_id": record_id})
    if doc:
        if doc["status"] != "valid":
            raise AppError("This image failed validation and has no preview", 404, "no_preview")
        keys, modality = doc["file_paths"], doc["modality"]
    else:
        doc = ctx.store.find_one("augmented_samples", {"sample_id": record_id})
        if not doc:
            raise not_found("Image", record_id)
        if not doc.get("output_path"):
            raise AppError("This sample was rejected and no file was written", 404, "no_preview")
        keys, modality = [doc["output_path"]], doc["modality"]
    img = load_image_set([ctx.storage.path(k) for k in keys], modality)
    return render_array(img, channel=channel, slice_index=slice_index, axis=axis, modality=modality, window=window, max_size=max_size)
