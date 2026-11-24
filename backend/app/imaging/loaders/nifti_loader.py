"""NIfTI-1 reading/writing.

Uses nibabel when installed. Otherwise falls back to a small built-in NIfTI-1
implementation (uncompressed or gzip, common dtypes, sform/qform affines) so the
platform and its test-suite work without optional dependencies.
"""
from __future__ import annotations

import gzip
import struct
from pathlib import Path

import numpy as np

from ..types import ImageData, ImageLoadError

_CODES = {2: np.uint8, 4: np.int16, 8: np.int32, 16: np.float32, 64: np.float64, 256: np.int8, 512: np.uint16, 768: np.uint32}
_DTYPE_TO_CODE = {np.dtype(v): k for k, v in _CODES.items()}


def _nib():
    try:
        import nibabel
        return nibabel
    except ImportError:
        return None


def _spacing(affine: np.ndarray) -> tuple[float, float, float]:
    return tuple(round(float(x), 5) for x in np.sqrt((np.asarray(affine)[:3, :3] ** 2).sum(axis=0)))  # type: ignore[return-value]


# ----------------------------------------------------------------- fallback IO
def _qform_affine(b: float, c: float, d: float, off: tuple, pix: tuple, qfac: float) -> np.ndarray:
    a = np.sqrt(max(0.0, 1.0 - (b * b + c * c + d * d)))
    rot = np.array([
        [a * a + b * b - c * c - d * d, 2 * (b * c - a * d), 2 * (b * d + a * c)],
        [2 * (b * c + a * d), a * a + c * c - b * b - d * d, 2 * (c * d - a * b)],
        [2 * (b * d - a * c), 2 * (c * d + a * b), a * a + d * d - c * c - b * b],
    ])
    aff = np.eye(4)
    aff[:3, :3] = rot * np.array([pix[0], pix[1], pix[2] * (qfac if qfac else 1.0)])
    aff[:3, 3] = off
    return aff


def _read_builtin(path: Path) -> tuple[np.ndarray, np.ndarray, str]:
    raw = (gzip.open(path, "rb") if path.name.endswith(".gz") else open(path, "rb")).read()
    if len(raw) < 352:
        raise ImageLoadError("File too small to be a NIfTI-1 image")
    end = "<" if struct.unpack_from("<i", raw, 0)[0] == 348 else ">"
    if struct.unpack_from(end + "i", raw, 0)[0] != 348:
        raise ImageLoadError("Not a NIfTI-1 file (bad header size); NIfTI-2 requires nibabel")
    dim = struct.unpack_from(end + "8h", raw, 40)
    datatype = struct.unpack_from(end + "h", raw, 70)[0]
    pixdim = struct.unpack_from(end + "8f", raw, 76)
    vox_offset = int(struct.unpack_from(end + "f", raw, 108)[0])
    slope, inter = struct.unpack_from(end + "2f", raw, 112)
    qcode, scode = struct.unpack_from(end + "2h", raw, 252)
    if datatype not in _CODES:
        raise ImageLoadError(f"Unsupported NIfTI datatype code {datatype}")
    ndim = dim[0]
    if not 3 <= ndim <= 4:
        raise ImageLoadError(f"Expected a 3D or 4D NIfTI volume, found {ndim}D")
    shape = tuple(int(x) for x in dim[1 : ndim + 1])
    dt = np.dtype(_CODES[datatype]).newbyteorder(end)
    count = int(np.prod(shape))
    if len(raw) < vox_offset + count * dt.itemsize:
        raise ImageLoadError("NIfTI data block is truncated")
    arr = np.frombuffer(raw, dtype=dt, count=count, offset=vox_offset).reshape(shape, order="F")
    native = str(np.dtype(_CODES[datatype]))
    if slope not in (0.0,) and not (slope == 1.0 and inter == 0.0) and np.isfinite(slope):
        arr = arr.astype(np.float32) * slope + inter
    else:
        arr = arr.astype(arr.dtype.newbyteorder("="))
    if scode > 0:
        srow = struct.unpack_from(end + "12f", raw, 280)
        affine = np.vstack([np.array(srow).reshape(3, 4), [0, 0, 0, 1]])
    elif qcode > 0:
        b, c, d, ox, oy, oz = struct.unpack_from(end + "6f", raw, 256)
        affine = _qform_affine(b, c, d, (ox, oy, oz), pixdim[1:4], pixdim[0])
    else:
        affine = np.diag([pixdim[1] or 1.0, pixdim[2] or 1.0, pixdim[3] or 1.0, 1.0])
    return arr, affine, native


def _write_builtin(path: Path, arr: np.ndarray, affine: np.ndarray) -> None:
    dtype = np.dtype(arr.dtype)
    if dtype not in _DTYPE_TO_CODE:
        arr, dtype = arr.astype(np.float32), np.dtype(np.float32)
    hdr = bytearray(352)
    struct.pack_into("<i", hdr, 0, 348)
    dims = [arr.ndim, *arr.shape] + [1] * (7 - arr.ndim)
    struct.pack_into("<8h", hdr, 40, *dims)
    struct.pack_into("<h", hdr, 70, _DTYPE_TO_CODE[dtype])
    struct.pack_into("<h", hdr, 72, dtype.itemsize * 8)
    sp = _spacing(affine)
    struct.pack_into("<8f", hdr, 76, 1.0, sp[0], sp[1], sp[2], 1.0, 1.0, 1.0, 1.0)
    struct.pack_into("<f", hdr, 108, 352.0)
    struct.pack_into("<2f", hdr, 112, 1.0, 0.0)
    hdr[123] = 2  # xyzt_units: millimetres
    struct.pack_into("<2h", hdr, 252, 0, 1)  # qform_code=0, sform_code=1 (scanner anatomical)
    struct.pack_into("<12f", hdr, 280, *np.asarray(affine, dtype=float)[:3, :].ravel())
    hdr[344:348] = b"n+1\x00"
    payload = bytes(hdr) + np.asarray(arr, dtype=dtype.newbyteorder("<")).tobytes(order="F")
    if path.name.endswith(".gz"):
        with gzip.GzipFile(path, "wb", compresslevel=3, mtime=0) as fh:  # mtime=0 keeps output byte-reproducible
            fh.write(payload)
    else:
        path.write_bytes(payload)


# ------------------------------------------------------------------ public API
def load_nifti(path: Path, modality: str) -> ImageData:
    path = Path(path)
    nib = _nib()
    try:
        if nib is not None:
            img = nib.load(str(path))
            arr = np.asarray(img.get_fdata(dtype=np.float32))
            affine, native = np.asarray(img.affine, dtype=float), str(img.get_data_dtype())
        else:
            arr, affine, native = _read_builtin(path)
    except ImageLoadError:
        raise
    except Exception as exc:
        raise ImageLoadError(f"Cannot read NIfTI file: {exc}") from exc
    if arr.ndim == 4:
        arr = np.moveaxis(arr, -1, 0)  # (X,Y,Z,C) -> (C,X,Y,Z); a single sequence stays 4D until the adapter squeezes it
        if arr.shape[0] == 1:
            arr = arr[0]
    elif arr.ndim != 3:
        raise ImageLoadError(f"Expected a 3D or 4D NIfTI volume, found {arr.ndim}D")
    return ImageData(array=np.ascontiguousarray(arr), modality=modality, spatial_ndim=3, spacing=_spacing(affine),
                     affine=affine, fmt="nifti", source_dtype=native, meta={"nifti_backend": "nibabel" if nib else "builtin"})


def save_nifti(path: Path, arr: np.ndarray, affine: np.ndarray, dtype: str | None = None) -> None:
    path = Path(path)
    data = np.asarray(arr)
    if dtype:
        from ..types import restore_dtype
        data = restore_dtype(data, dtype)
    if data.ndim == 4:
        data = np.moveaxis(data, 0, -1)  # (C,X,Y,Z) -> (X,Y,Z,C)
    nib = _nib()
    if nib is not None:
        img = nib.Nifti1Image(data, np.asarray(affine, dtype=float))
        img.header.set_data_dtype(data.dtype)
        nib.save(img, str(path))
    else:
        _write_builtin(path, data, np.asarray(affine, dtype=float))
