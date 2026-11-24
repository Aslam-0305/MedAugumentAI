from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ...schemas.requests import ExportRequest
from ...services import export_service
from ...utils.common import AppError
from ..deps import get_ctx

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", status_code=202)
def create(body: ExportRequest, ctx=Depends(get_ctx)):
    return export_service.create_export(ctx, body.job_id, include_originals=body.include_originals,
                                        include_validation_test=body.include_validation_test, include_warnings=body.include_warnings)


@router.get("")
def list_exports(dataset_id: str | None = None, ctx=Depends(get_ctx)):
    return export_service.list_exports(ctx, dataset_id)


@router.get("/{export_id}")
def get(export_id: str, ctx=Depends(get_ctx)):
    doc = export_service.public_export(export_service.get_export(ctx, export_id))
    if doc["status"] == "completed":
        doc["download_url"] = f"/api/v1/exports/{export_id}/download"
    return doc


@router.get("/{export_id}/download")
def download(export_id: str, ctx=Depends(get_ctx)):
    doc = export_service.get_export(ctx, export_id)
    if doc["status"] != "completed" or not doc.get("archive_path"):
        raise AppError("Export is not ready", 409, "conflict")
    path = ctx.storage.path(doc["archive_path"])
    return FileResponse(path, media_type="application/zip", filename=path.name)
