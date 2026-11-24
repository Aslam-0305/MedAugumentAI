"""Augmentation pipeline: config parsing + execution of one randomised variant."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..utils.common import AppError
from .adapters import ModalityAdapter, get_adapter
from .transforms.intensity import INTENSITY_FUNCS, apply_erasing_box, sample_erasing_box
from .transforms.registry import INTENSITY_ORDER, REGISTRY
from .transforms.spatial import ORDERS, Resampler, sample_spatial
from .types import ImageData, restore_dtype

INTERPOLATIONS = ("nearest", "linear", "cubic")
PADDINGS = ("background", "edge", "reflect")


@dataclass
class TransformSpec:
    name: str
    probability: float
    params: dict


@dataclass
class PipelineConfig:
    modality: str
    transforms: list[TransformSpec]
    interpolation: str = "linear"
    padding: str = "background"
    output_dtype: str = "preserve"  # "preserve" | "float32"
    allow_laterality_flip: bool = False
    min_transforms: int = 1
    max_transforms: int | None = None

    def to_dict(self) -> dict:
        return {
            "modality": self.modality,
            "transforms": [{"name": t.name, "probability": t.probability, "params": t.params} for t in self.transforms],
            "interpolation": self.interpolation, "padding": self.padding, "output_dtype": self.output_dtype,
            "allow_laterality_flip": self.allow_laterality_flip,
            "min_transforms": self.min_transforms, "max_transforms": self.max_transforms,
        }


def parse_pipeline_config(modality: str, raw: dict | None) -> tuple[PipelineConfig, list[str]]:
    """Validate a user config against the modality policy; returns the normalised config + warnings."""
    raw = raw or {}
    adapter = get_adapter(modality)
    warnings: list[str] = []
    interpolation = raw.get("interpolation", "linear")
    padding = raw.get("padding", "background")
    out_dtype = raw.get("output_dtype", "preserve")
    if interpolation not in INTERPOLATIONS:
        raise AppError(f"interpolation must be one of {INTERPOLATIONS}", 400, "invalid_config")
    if padding not in PADDINGS:
        raise AppError(f"padding must be one of {PADDINGS}", 400, "invalid_config")
    if out_dtype not in ("preserve", "float32"):
        raise AppError("output_dtype must be 'preserve' or 'float32'", 400, "invalid_config")
    if raw.get("materialization", "materialized") != "materialized":
        raise AppError("Only materialized output is supported in this release (on-the-fly augmentation is not implemented)", 400, "not_supported")
    allow_flip = bool(raw.get("allow_laterality_flip", False))

    requested = raw.get("transforms") or [{"name": n} for n in adapter.default_enabled]
    seen, specs = set(), []
    for item in requested:
        name = item["name"] if isinstance(item, dict) else str(item)
        if name in seen:
            raise AppError(f"Transform '{name}' is listed twice", 400, "invalid_config")
        seen.add(name)
        adapter.check_allowed(name)
        if name == "flip" and not allow_flip:
            raise AppError("The left-right flip changes laterality. Enable 'allow_laterality_flip' only if your task is invariant to it.", 400, "laterality_flip_blocked")
        user = item if isinstance(item, dict) else {}
        params, warns = adapter.resolve_params(name, user.get("params"))
        warnings += warns
        prob = float(user.get("probability", REGISTRY[name].probability))
        if not 0 <= prob <= 1:
            raise AppError(f"probability for '{name}' must be between 0 and 1", 400, "invalid_config")
        specs.append(TransformSpec(name, prob, params))
        if REGISTRY[name].caution:
            warnings.append(f"{REGISTRY[name].label}: {REGISTRY[name].caution}")
    if not specs:
        raise AppError("Select at least one transform", 400, "invalid_config")
    min_t = int(raw.get("min_transforms", 1))
    max_t = raw.get("max_transforms")
    if min_t < 0 or min_t > len(specs):
        raise AppError("min_transforms must be between 0 and the number of selected transforms", 400, "invalid_config")
    return PipelineConfig(modality, specs, interpolation, padding, out_dtype, allow_flip, min_t, int(max_t) if max_t else None), warnings


class AugmentationPipeline:
    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.adapter: ModalityAdapter = get_adapter(cfg.modality)

    def _choose(self, rng: np.random.Generator) -> list[TransformSpec]:
        specs = self.cfg.transforms
        chosen = [s for s in specs if rng.random() < s.probability]
        if len(chosen) < self.cfg.min_transforms:  # top up with unchosen ones, highest probability first
            rest = sorted((s for s in specs if s not in chosen), key=lambda s: (-s.probability, rng.random()))
            chosen += rest[: self.cfg.min_transforms - len(chosen)]
        if self.cfg.max_transforms and len(chosen) > self.cfg.max_transforms:
            idx = rng.permutation(len(chosen))[: self.cfg.max_transforms]
            chosen = [chosen[i] for i in sorted(idx)]
        return chosen

    def run(self, src: ImageData, rng: np.random.Generator) -> tuple[ImageData, list[dict]]:
        cfg, adapter = self.cfg, self.adapter
        chosen = self._choose(rng)
        history: list[dict] = []
        chans = [c.astype(np.float32) for c in src.channels()]
        mask = src.mask
        shape = src.spatial_shape

        spatial = {s.name: s.params for s in chosen if REGISTRY[s.name].kind == "spatial"}
        if spatial:
            conc = sample_spatial(spatial, rng, shape, adapter.left_right_axis(src))
            rs = Resampler(shape, src.spacing, conc)
            order = ORDERS[cfg.interpolation]
            new = []
            for ch in chans:
                mode, cval = adapter.pad_value(ch, cfg.padding)
                new.append(rs.apply(ch, order=order, mode=mode, cval=cval))
            chans = new
            if mask is not None:
                mask = rs.apply(mask, order=0, mode="constant", cval=0)
            record = {"flip": {"axis": conc.get("flip_axis")}, "rotate": {"angles_deg": conc.get("angles_deg")},
                      "translate": {"fraction": conc.get("translate_fraction")}, "scale": {"factor": conc.get("scale")},
                      "elastic": conc.get("elastic")}
            for name in spatial:
                history.append({"name": name, "family": REGISTRY[name].family, "params": spatial[name], "sampled": record[name]})

        ctx = {"modality": cfg.modality, "spacing": src.spacing}
        by_name = {s.name: s for s in chosen}
        for name in INTENSITY_ORDER:
            spec = by_name.get(name)
            if spec is None:
                continue
            if name == "random_erasing":
                box = sample_erasing_box(spec.params, rng, shape, mask)
                chans = [apply_erasing_box(ch, box) for ch in chans]
                history.append({"name": name, "family": "occlusion", "params": spec.params, "sampled": box})
                continue
            sampled = []
            for i, ch in enumerate(chans):
                chans[i], info = INTENSITY_FUNCS[name](ch, spec.params, rng, ctx)
                sampled.append(info)
            history.append({"name": name, "family": REGISTRY[name].family, "params": spec.params,
                            "sampled": sampled[0] if len(sampled) == 1 else sampled})

        arr = np.stack(chans, axis=0) if src.has_channels else chans[0]
        arr = restore_dtype(arr, src.source_dtype) if cfg.output_dtype == "preserve" else arr.astype(np.float32)
        return src.replace(array=arr, mask=mask), history
