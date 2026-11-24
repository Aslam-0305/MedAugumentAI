"""Geometric + elastic transforms for 2D images and 3D volumes (any number of channels).

All spatial transforms of one sample are composed into a *single* resampling step to
avoid cumulative interpolation blur, and the identical mapping is applied to the image
(chosen interpolation) and the mask (nearest neighbour). Rotation/scale are defined in
physical space (using voxel spacing) so anisotropic CT/MRI voxels are not sheared.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

ORDERS = {"nearest": 0, "linear": 1, "cubic": 3}


def _rotation(nd: int, angles_deg: list[float]) -> np.ndarray:
    if nd == 2:
        t = np.deg2rad(angles_deg[0])
        return np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    ax, ay, az = np.deg2rad(angles_deg)
    rx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    ry = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    rz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    return rz @ ry @ rx


def sample_spatial(active: dict[str, dict], rng: np.random.Generator, shape: tuple[int, ...], flip_axis: int) -> dict:
    """Draw concrete values for every active spatial transform (recorded in provenance)."""
    nd = len(shape)
    c: dict = {}
    if "flip" in active:
        c["flip_axis"] = flip_axis
    if "rotate" in active:
        m = float(active["rotate"]["max_degrees"])
        if nd == 2:
            c["angles_deg"] = [float(rng.uniform(-m, m))]
        else:
            axes = active["rotate"].get("axes", [0, 1, 2])
            c["angles_deg"] = [float(rng.uniform(-m, m)) if i in axes else 0.0 for i in range(3)]
    if "translate" in active:
        f = float(active["translate"]["max_fraction"])
        c["translate_fraction"] = [float(v) for v in rng.uniform(-f, f, size=nd)]
    if "scale" in active:
        lo, hi = active["scale"]["range"]
        c["scale"] = float(rng.uniform(lo, hi))
    if "elastic" in active:
        e = active["elastic"]
        c["elastic"] = {"max_displacement": float(e["max_displacement"]), "smoothness": float(e["smoothness"]),
                        "seed": int(rng.integers(0, 2**31 - 1))}
    return c


def _smooth_field(shape: tuple[int, ...], smoothness: float, rng: np.random.Generator) -> np.ndarray:
    """Smooth random field in [-1, 1], computed on a coarse grid and upsampled (cheap for 3D)."""
    ds = max(1, int(smoothness // 2))
    low = tuple(max(2, int(np.ceil(s / ds))) for s in shape)
    f = ndi.gaussian_filter(rng.uniform(-1, 1, size=low).astype(np.float32), sigma=max(smoothness / ds, 0.5), mode="reflect")
    f = ndi.zoom(f, [s / l for s, l in zip(shape, low)], order=1)
    if f.shape != tuple(shape):  # float rounding in zoom: crop / edge-pad to exact size
        f = f[tuple(slice(0, s) for s in shape)]
        f = np.pad(f, [(0, s - fs) for s, fs in zip(shape, f.shape)], mode="edge")
    peak = np.abs(f).max()
    return f / peak if peak > 0 else f


class Resampler:
    """Builds the mapping once; `apply` resamples any array of the same spatial shape."""

    def __init__(self, shape: tuple[int, ...], spacing: tuple[float, ...], c: dict):
        nd = len(shape)
        sp = np.asarray(spacing, dtype=float)
        center = (np.asarray(shape, dtype=float) - 1) / 2
        lin = np.eye(nd)
        if "angles_deg" in c:
            lin = _rotation(nd, c["angles_deg"]) @ lin
        if "scale" in c:
            lin = c["scale"] * lin
        lin_vox = np.diag(1 / sp) @ lin @ np.diag(sp)  # physical-space linear map expressed in voxel units
        shift = np.asarray(c.get("translate_fraction", [0.0] * nd)) * np.asarray(shape)
        self.matrix = np.linalg.inv(lin_vox)  # output voxel -> input voxel
        self.offset = center - self.matrix @ (center + shift)
        self.shape = tuple(shape)
        self.disp: np.ndarray | None = None
        self._coords: np.ndarray | None = None
        if "elastic" in c:
            e = c["elastic"]
            rng = np.random.default_rng(e["seed"])
            self.disp = np.stack([_smooth_field(shape, e["smoothness"], rng) * (e["max_displacement"] / sp[i]) for i in range(nd)])
        self.flip_axis = c.get("flip_axis")
        self.is_identity = self.disp is None and np.allclose(self.matrix, np.eye(nd)) and np.allclose(self.offset, 0)

    def apply(self, arr: np.ndarray, *, order: int, mode: str, cval: float) -> np.ndarray:
        if self.flip_axis is not None:
            arr = np.flip(arr, axis=self.flip_axis)
        if self.is_identity:
            return np.ascontiguousarray(arr)
        if self.disp is None:
            return ndi.affine_transform(arr, self.matrix, self.offset, order=order, mode=mode, cval=cval)
        if self._coords is None:
            grid = np.indices(self.shape, dtype=np.float32)
            base = np.tensordot(self.matrix.astype(np.float32), grid, axes=(1, 0))
            self._coords = base + self.offset.astype(np.float32).reshape((-1,) + (1,) * len(self.shape)) + self.disp
        return ndi.map_coordinates(arr, self._coords, order=order, mode=mode, cval=cval)
