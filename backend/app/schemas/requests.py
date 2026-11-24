"""Request bodies. Services receive plain dicts (model_dump) so they stay framework-independent."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class BalancingIn(BaseModel):
    strategy: Literal["target_count", "balance_largest", "custom"] = "balance_largest"
    target_count: int | None = Field(None, ge=1)
    custom_targets: dict[str, int] = Field(default_factory=dict)
    max_expansion_factor: float = Field(10.0, ge=1)
    per_class_cap: int | None = Field(None, ge=0)
    max_total_additional: int | None = Field(None, ge=1)
    excluded_classes: list[str] = Field(default_factory=list)


class TransformIn(BaseModel):
    name: str
    probability: float | None = Field(None, ge=0, le=1)
    params: dict[str, Any] = Field(default_factory=dict)


class AugmentationIn(BaseModel):
    transforms: list[TransformIn] = Field(default_factory=list, description="Empty = modality defaults")
    interpolation: Literal["nearest", "linear", "cubic"] = "linear"
    padding: Literal["background", "edge", "reflect"] = "background"
    output_dtype: Literal["preserve", "float32"] = "preserve"
    allow_laterality_flip: bool = False
    min_transforms: int = Field(1, ge=0)
    max_transforms: int | None = Field(None, ge=1)
    materialization: Literal["materialized", "on_the_fly"] = "materialized"


class PlanRequest(BaseModel):
    dataset_id: str
    balancing: BalancingIn = Field(default_factory=BalancingIn)
    augmentation: AugmentationIn | None = None


class JobCreate(PlanRequest):
    seed: int | None = Field(None, ge=0, lt=2**31)
    name: str | None = Field(None, max_length=120)


class PreviewRequest(BaseModel):
    dataset_id: str
    image_id: str
    augmentation: AugmentationIn | None = None
    seed: int = 0
    channel: int = Field(0, ge=0)
    slice_index: int | None = Field(None, ge=0)


class SplitRequest(BaseModel):
    mode: Literal["create", "use_existing"] = "create"
    ratios: dict[str, float] | None = None
    seed: int = 42


class ExportRequest(BaseModel):
    job_id: str
    include_originals: bool = True
    include_validation_test: bool = True
    include_warnings: bool = True


class SamplePatch(BaseModel):
    review_status: Literal["accepted", "rejected", "auto"]


def dump(model: BaseModel | None) -> dict | None:
    return model.model_dump(exclude_none=True) if model is not None else None
