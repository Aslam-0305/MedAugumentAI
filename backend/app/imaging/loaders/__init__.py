"""Format-detecting loader front-end."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..types import ImageData, ImageLoadError, restore_dtype
from .dicom_loader import is_dicom_file, load_dicom_file, load_dicom_series
from .image_2d import EXT_2D, load_2d, output_extension_2d, save_2d
from .nifti_loader import load_nifti, save_nifti

__all__ = ["detect_format", "load_image", "load_image_set", "save_image", "is_image_candidate"]


def detect_format(path: Path) -> str | None:
    path = Path(path)
    if path.is_dir():
        return "dicom_series"
    name = path.name.lower()
    if name.endswith((".nii", ".nii.gz")):
        return "nifti"
    if path.suffix.lower() == ".dcm":
        return "dicom"
    if path.suffix.lower() in EXT_2D:
        return "2d"
    if not path.suffix and is_dicom_file(path):
        return "dicom"
    return None


def is_image_candidate(path: Path) -> bool:
    return detect_format(path) is not None


def load_image(path: Path, modality: str) -> ImageData:
    path = Path(path)
    if not path.exists():
        raise ImageLoadError("File not found")
    fmt = detect_format(path)
    if fmt == "2d":
        return load_2d(path, modality)
    if fmt == "nifti":
        return load_nifti(path, modality)
    if fmt == "dicom":
        return load_dicom_file(path, modality)
    if fmt == "dicom_series":
        return load_dicom_series(path, modality)
    raise ImageLoadError(f"Unsupported file type: {path.name}")


def load_image_set(paths: list[Path], modality: str) -> ImageData:
    """Load several aligned sequences (MRI) and stack them as channels."""
    images = [load_image(p, modality) for p in paths]
    if len(images) == 1:
        return images[0]
    base = images[0]
    for p, im in zip(paths[1:], images[1:]):
        if im.spatial_ndim != 3 or base.spatial_ndim != 3:
            raise ImageLoadError("Multi-sequence input requires 3D volumes")
        if im.has_channels or base.has_channels:
            raise ImageLoadError("Provide either one 4D file or several 3D files, not both")
        if im.spatial_shape != base.spatial_shape:
            raise ImageLoadError(f"Sequence '{Path(p).name}' has shape {im.spatial_shape}, expected {base.spatial_shape}")
        if not np.allclose(im.affine, base.affine, atol=1e-3):
            raise ImageLoadError(f"Sequence '{Path(p).name}' is not spatially aligned (affine differs)")
    stacked = np.stack([im.array for im in images], axis=0)
    return base.replace(array=stacked, meta={**base.meta, "sequences": len(images)})


def save_image(dest_dir: Path, stem: str, array: np.ndarray, like: ImageData) -> Path:
    """Write `array` using `like`'s geometry; returns the written path. Never overwrites an existing file."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if like.spatial_ndim == 2:
        out = dest_dir / f"{stem}{output_extension_2d(array.dtype)}"
        if out.exists():
            raise FileExistsError(out)
        save_2d(out, array)
    else:
        out = dest_dir / f"{stem}.nii.gz"
        if out.exists():
            raise FileExistsError(out)
        save_nifti(out, array, like.affine if like.affine is not None else np.eye(4))
    return out
