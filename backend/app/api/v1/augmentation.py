from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ...schemas.requests import JobCreate, PlanRequest, PreviewRequest, dump
from ...services import augmentation_service
from ..deps import get_ctx

router = APIRouter(prefix="/augmentation", tags=["augmentation"])


@router.get("/transforms", summary="Transforms allowed for a modality, with defaults, limits and cautions")
def transforms(modality: str):
    return augmentation_service.transform_catalog(modality)


@router.post("/plan", summary="Projected per-class augmentation plan (nothing is created)")
def plan(body: PlanRequest, ctx=Depends(get_ctx)):
    return augmentation_service.build_plan(ctx, body.dataset_id, dump(body.balancing), dump(body.augmentation))


@router.post("/jobs", status_code=202, summary="Create and queue an augmentation job")
def create_job(body: JobCreate, ctx=Depends(get_ctx)):
    return augmentation_service.create_job(ctx, body.dataset_id, dump(body.balancing), dump(body.augmentation), seed=body.seed, name=body.name)


@router.post("/preview", summary="One throw-away augmented example as PNG (not stored)", response_class=Response,
             responses={200: {"content": {"image/png": {}}}})
def preview(body: PreviewRequest, ctx=Depends(get_ctx)):
    png = augmentation_service.preview_augmentation(ctx, body.dataset_id, body.image_id, dump(body.augmentation), body.seed, body.channel, body.slice_index)
    return Response(png, media_type="image/png")
