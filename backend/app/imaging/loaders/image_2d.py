"""PNG / JPEG / TIFF loading and saving for 2D radiographs (Pillow)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..types import ImageData, ImageLoadError

EXT_2D = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def load_2d(path: Path, modality: str = "xray") -> ImageData:
    path = Path(path)
    meta: dict = {}
    try:
        with Image.open(path) as im:
            fmt = (im.format or path.suffix.lstrip(".")).lower()
            im.load()
            mode = im.mode
            if mode in ("I;16", "I;16L", "I;16B", "I;16N"):
                arr = np.array(im).astype(np.uint16, copy=False)
            elif mode == "I":
                arr = np.array(im)
                arr = arr.astype(np.uint16) if arr.min() >= 0 and arr.max() <= 65535 else arr.astype(np.float32)
            elif mode == "F":
                arr = np.array(im, dtype=np.float32)
            elif mode == "L":
                arr = np.array(im, dtype=np.uint8)
            else:  # RGB, RGBA, P, 1, LA ... -> single-channel grey
                meta["converted_from_mode"] = mode
                arr = np.array(im.convert("L"), dtype=np.uint8)
    except Exception as exc:
        raise ImageLoadError(f"Cannot decode image: {exc}") from exc
    if arr.ndim != 2:
        raise ImageLoadError(f"Expected a 2D image, got shape {arr.shape}")
    return ImageData(array=np.ascontiguousarray(arr), modality=modality, spatial_ndim=2, spacing=(1.0, 1.0), fmt=fmt, meta=meta)


def output_extension_2d(dtype: np.dtype | str) -> str:
    return ".png" if np.dtype(dtype) in (np.dtype(np.uint8), np.dtype(np.uint16)) else ".tiff"


def save_2d(path: Path, arr: np.ndarray) -> None:
    """Lossless write. uint8/uint16 -> PNG; anything else -> float32 TIFF."""
    path = Path(path)
    if arr.dtype in (np.uint8, np.uint16):
        Image.fromarray(arr).save(path, format="PNG")
    else:
        Image.fromarray(arr.astype(np.float32), mode="F").save(path, format="TIFF")
