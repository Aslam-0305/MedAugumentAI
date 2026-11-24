"""DICOM loading via pydicom (optional dependency).

* 2D radiographs: one .dcm file -> one image.
* CT/MRI: a directory of slices -> one volume. Slices are grouped by SeriesInstanceUID,
  sorted along the slice normal using ImagePositionPatient, and the voxel->world affine
  is rebuilt from the DICOM geometry (converted to RAS to match NIfTI conventions).

Only an allow-list of non-identifying attributes is returned; PHI is detected (tag
names only, never values) so the UI can warn the user.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..metadata import PHI_TAGS, SAFE_DICOM_FIELDS
from ..types import ImageData, ImageLoadError, MissingDependencyError


def _pydicom():
    try:
        import pydicom
        return pydicom
    except ImportError as exc:
        raise MissingDependencyError("pydicom is required to read DICOM files (pip install pydicom)") from exc


def is_dicom_file(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            fh.seek(128)
            return fh.read(4) == b"DICM"
    except OSError:
        return False


def _safe_meta(ds) -> dict:
    meta = {}
    for name in SAFE_DICOM_FIELDS:
        val = ds.get(name)
        if val is not None and str(val) != "":
            meta[name] = float(val) if name.startswith(("Rescale", "SliceThickness")) else str(val)
    meta["phi_tags"] = [t for t in PHI_TAGS if str(ds.get(t, "")).strip() not in ("", "None")]
    return meta


def _pixels(ds) -> np.ndarray:
    try:
        arr = ds.pixel_array
    except Exception as exc:  # compressed transfer syntaxes need extra handlers
        raise ImageLoadError(f"Cannot decode DICOM pixel data: {exc}") from exc
    slope, inter = float(ds.get("RescaleSlope", 1) or 1), float(ds.get("RescaleIntercept", 0) or 0)
    if slope != 1.0 or inter != 0.0:
        arr = arr.astype(np.float32) * slope + inter
    if str(ds.get("PhotometricInterpretation", "")) == "MONOCHROME1":  # 0 = white -> invert to MONOCHROME2
        if np.issubdtype(arr.dtype, np.integer):
            bits = int(ds.get("BitsStored", arr.dtype.itemsize * 8))
            arr = ((1 << bits) - 1) - arr
        else:
            arr = (arr.max() + arr.min()) - arr
    return arr


def load_dicom_file(path: Path, modality: str = "xray") -> ImageData:
    pd = _pydicom()
    try:
        ds = pd.dcmread(str(path))
    except Exception as exc:
        raise ImageLoadError(f"Cannot parse DICOM file: {exc}") from exc
    arr = _pixels(ds)
    if arr.ndim == 3 and int(ds.get("SamplesPerPixel", 1)) == 3:
        arr = (arr[..., :3] @ np.array([0.299, 0.587, 0.114])).astype(np.uint8)
    if arr.ndim != 2:
        raise ImageLoadError(f"Expected a single 2D frame, got shape {arr.shape}; pass multi-frame data as a series")
    ps = ds.get("PixelSpacing") or ds.get("ImagerPixelSpacing") or [1.0, 1.0]
    return ImageData(array=np.ascontiguousarray(arr), modality=modality, spatial_ndim=2,
                     spacing=(float(ps[0]), float(ps[1])), fmt="dicom", meta=_safe_meta(ds))


def load_dicom_series(path: Path, modality: str) -> ImageData:
    pd = _pydicom()
    files = sorted(p for p in Path(path).rglob("*") if p.is_file() and (p.suffix.lower() == ".dcm" or is_dicom_file(p)))
    if not files:
        raise ImageLoadError("No DICOM files found in series directory")
    slices = []
    for f in files:
        try:
            slices.append(pd.dcmread(str(f)))
        except Exception as exc:
            raise ImageLoadError(f"Cannot parse DICOM slice {f.name}: {exc}") from exc
    uids = {str(getattr(s, "SeriesInstanceUID", "")) for s in slices}
    if len(uids) > 1:
        raise ImageLoadError(f"Directory mixes {len(uids)} DICOM series; keep one series per directory")
    if any(not hasattr(s, "ImagePositionPatient") or not hasattr(s, "ImageOrientationPatient") for s in slices):
        raise ImageLoadError("Slices lack ImagePositionPatient/ImageOrientationPatient; cannot order them into a volume")
    iop = np.array(slices[0].ImageOrientationPatient, dtype=float)
    row_dir, col_dir = iop[:3], iop[3:]
    normal = np.cross(row_dir, col_dir)
    slices.sort(key=lambda s: float(np.dot(np.array(s.ImagePositionPatient, dtype=float), normal)))
    pos = np.array([float(np.dot(np.array(s.ImagePositionPatient, dtype=float), normal)) for s in slices])
    if len(pos) > 1:
        gaps = np.diff(pos)
        if np.any(gaps <= 1e-6):
            raise ImageLoadError("Duplicate slice positions in series")
        dz = float(np.median(gaps))
        if np.max(np.abs(gaps - dz)) > 0.05 * abs(dz):
            raise ImageLoadError("Non-uniform slice spacing; resample the series to a regular grid first")
    else:
        dz = float(slices[0].get("SliceThickness", 1.0) or 1.0)
    shapes = {(int(s.Rows), int(s.Columns)) for s in slices}
    if len(shapes) != 1:
        raise ImageLoadError("Slices in the series have different in-plane sizes")
    vol = np.stack([_pixels(s).T for s in slices], axis=-1)  # (cols, rows, slices) == (X, Y, Z)
    ps = slices[0].get("PixelSpacing") or [1.0, 1.0]
    lps = np.eye(4)
    lps[:3, 0], lps[:3, 1], lps[:3, 2] = row_dir * float(ps[1]), col_dir * float(ps[0]), normal * dz
    lps[:3, 3] = np.array(slices[0].ImagePositionPatient, dtype=float)
    affine = np.diag([-1.0, -1.0, 1.0, 1.0]) @ lps  # LPS (DICOM) -> RAS (NIfTI)
    meta = _safe_meta(slices[0])
    meta["n_slices"] = len(slices)
    return ImageData(array=np.ascontiguousarray(vol), modality=modality, spatial_ndim=3,
                     spacing=(float(ps[1]), float(ps[0]), abs(dz)), affine=affine, fmt="dicom_series",
                     source_dtype=str(vol.dtype), meta=meta)
