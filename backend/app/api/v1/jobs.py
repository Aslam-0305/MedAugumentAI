from __future__ import annotations

from fastapi import APIRouter, Depends

from ...schemas.requests import SamplePatch
from ...services import job_service
from ..deps import get_ctx

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(dataset_id: str | None = None, ctx=Depends(get_ctx)):
    return job_service.list_jobs(ctx, dataset_id)


@router.get("/{job_id}")
def get_job(job_id: str, ctx=Depends(get_ctx)):
    return job_service.get_job(ctx, job_id)


@router.post("/{job_id}/cancel")
def cancel(job_id: str, ctx=Depends(get_ctx)):
    return job_service.cancel_job(ctx, job_id)


@router.get("/{job_id}/results")
def results(job_id: str, status: str | None = None, skip: int = 0, limit: int = 24, ctx=Depends(get_ctx)):
    return job_service.job_results(ctx, job_id, status=status, skip=skip, limit=limit)


@router.get("/{job_id}/samples/{sample_id}")
def sample(job_id: str, sample_id: str, ctx=Depends(get_ctx)):
    return job_service.get_sample(ctx, job_id, sample_id)


@router.patch("/{job_id}/samples/{sample_id}", summary="Accept or reject an augmented sample after review")
def review(job_id: str, sample_id: str, body: SamplePatch, ctx=Depends(get_ctx)):
    return job_service.review_sample(ctx, job_id, sample_id, body.review_status)


@router.delete("/{job_id}", summary="Delete an augmentation job and its generated samples")
@router.post("/{job_id}/delete", summary="Delete an augmentation job (POST fallback)")
def delete_job(job_id: str, ctx=Depends(get_ctx)):
    job_service.delete_job(ctx, job_id)
    return {"status": "deleted", "job_id": job_id}

