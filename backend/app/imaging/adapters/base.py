"""Modality adapters: which transforms are allowed, hard parameter limits, defaults, input rules.

The same transform must not be applied indiscriminately to every modality (design §3),
so policy lives in data on each adapter and is enforced when a job is configured.
"""
from __future__ import annotations

import copy

import numpy as np

from ...utils.common import AppError
from ..transforms.registry import REGISTRY
from ..types import ImageData, orientation_codes


def issue(level: str, code: str, message: str) -> dict:
    return {"level": level, "code": code, "message": message}


class ModalityAdapter:
    modality = ""
    label = ""
    allowed: tuple[str, ...] = ()
    default_enabled: tuple[str, ...] = ()
    param_defaults: dict[str, dict] = {}   # per-modality overrides of registry defaults
    limits: dict[str, dict[str, tuple[float, float]]] = {}  # hard clamps
    policy_notes: tuple[str, ...] = ()
    blocked_reason: dict[str, str] = {}

    # ---- configuration ------------------------------------------------------
    def check_allowed(self, name: str) -> None:
        if name not in REGISTRY:
            raise AppError(f"Unknown transform '{name}'", 400, "unknown_transform")
        if name not in self.allowed:
            why = self.blocked_reason.get(name, "it is not appropriate for this modality")
            raise AppError(f"Transform '{name}' is not allowed for {self.label}: {why}", 400, "transform_not_allowed")

    def resolve_params(self, name: str, user: dict | None) -> tuple[dict, list[str]]:
        info = REGISTRY[name]
        params = copy.deepcopy(info.defaults)
        params.update(copy.deepcopy(self.param_defaults.get(name, {})))
        warnings: list[str] = []
        for key, value in (user or {}).items():
            if key not in params and not (name == "rotate" and key == "axes"):
                raise AppError(f"Transform '{name}' has no parameter '{key}'", 400, "unknown_parameter")
            params[key] = value
        if name == "rotate" and "axes" in params:
            axes = params["axes"]
            if not isinstance(axes, list) or any(a not in (0, 1, 2) for a in axes):
                raise AppError("rotate.axes must be a list drawn from 0, 1, 2", 400, "invalid_parameter")
        for key, (lo, hi) in self.limits.get(name, {}).items():
            val = params[key]
            clamped = [min(max(float(v), lo), hi) for v in val] if isinstance(val, (list, tuple)) else min(max(float(val), lo), hi)
            if clamped != val:
                warnings.append(f"{name}.{key} adjusted from {val} to {clamped} (allowed range for {self.label}: {lo}–{hi})")
            params[key] = clamped
        if name == "scale":
            lo_, hi_ = params["range"]
            if lo_ > hi_:
                params["range"] = [hi_, lo_]
        return params, warnings

    # ---- input / geometry rules --------------------------------------------------
    def validate_input(self, img: ImageData) -> list[dict]:
        out: list[dict] = []
        if not np.isfinite(img.array).all():
            out.append(issue("error", "non_finite", "Image contains NaN or Inf values"))
        for c, chan in enumerate(img.channels()):
            if float(chan.max()) == float(chan.min()):
                out.append(issue("warning", "constant_image", f"Channel {c} is constant (blank image)"))
        return out + self._modality_checks(img)

    def _modality_checks(self, img: ImageData) -> list[dict]:
        return []

    def pad_value(self, chan: np.ndarray, padding: str) -> tuple[str, float]:
        """(scipy mode, cval) used for voxels sampled from outside the field of view."""
        if padding == "edge":
            return "nearest", 0.0
        if padding == "reflect":
            return "reflect", 0.0
        return "constant", float(chan.min())

    def left_right_axis(self, img: ImageData) -> int:
        if img.spatial_ndim == 2:
            return 1
        codes = orientation_codes(img.affine) or "RAS"
        return next((i for i, c in enumerate(codes) if c in "LR"), 0)
