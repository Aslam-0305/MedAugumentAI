"""Core image container shared by loaders, adapters, transforms and validators.

Array conventions
  2D image            (H, W)
  3D volume           (X, Y, Z)           -- NIfTI index order
  multi-sequence MRI  (C, X, Y, Z)        -- channels first
`spatial_ndim` says whether the trailing axes are 2 or 3 spatial dimensions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MODALITIES = ("xray", "ct", "mri")


class ImageLoadError(ValueError):
    """The file exists but cannot be decoded / is structurally invalid."""


class MissingDependencyError(RuntimeError):
    """An optional library (pydicom, nibabel) is needed for this input."""


@dataclass
class ImageData:
    array: np.ndarray
    modality: str
    spatial_ndim: int
    spacing: tuple[float, ...]
    affine: np.ndarray | None = None  # 4x4 voxel->world for volumes
    mask: np.ndarray | None = None  # integer labels, spatial shape only
    fmt: str = "unknown"
    source_dtype: str = ""
    meta: dict = field(default_factory=dict)  # privacy-safe metadata only

    def __post_init__(self) -> None:
        if not self.source_dtype:
            self.source_dtype = str(self.array.dtype)

    @property
    def has_channels(self) -> bool:
        return self.array.ndim == self.spatial_ndim + 1

    @property
    def n_channels(self) -> int:
        return self.array.shape[0] if self.has_channels else 1

    @property
    def spatial_shape(self) -> tuple[int, ...]:
        return tuple(self.array.shape[-self.spatial_ndim :])

    def channels(self) -> list[np.ndarray]:
        return [self.array[c] for c in range(self.n_channels)] if self.has_channels else [self.array]

    def replace(self, **kw) -> "ImageData":
        data = dict(array=self.array, modality=self.modality, spatial_ndim=self.spatial_ndim, spacing=self.spacing,
                    affine=self.affine, mask=self.mask, fmt=self.fmt, source_dtype=self.source_dtype, meta=dict(self.meta))
        data.update(kw)
        return ImageData(**data)


def restore_dtype(arr: np.ndarray, dtype: str | np.dtype) -> np.ndarray:
    """Cast a float working array back to the source dtype (round + clip for integers)."""
    dt = np.dtype(dtype)
    if np.issubdtype(dt, np.integer):
        info = np.iinfo(dt)
        return np.clip(np.rint(arr), info.min, info.max).astype(dt)
    return arr.astype(dt)


def orientation_codes(affine: np.ndarray | None) -> str | None:
    """Axis codes such as 'RAS' derived from a voxel->world affine (None for 2D)."""
    if affine is None:
        return None
    rot = np.asarray(affine, dtype=float)[:3, :3]
    codes, used = [], set()
    for col in range(3):
        order = np.argsort(-np.abs(rot[:, col]))
        axis = next(a for a in order if a not in used)
        used.add(axis)
        pos, neg = (("R", "L"), ("A", "P"), ("S", "I"))[axis]
        codes.append(pos if rot[axis, col] >= 0 else neg)
    return "".join(codes)
