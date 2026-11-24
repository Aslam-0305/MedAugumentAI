from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from ...services import preview_service
from ..deps import get_ctx

router = APIRouter(prefix="/images", tags=["images"])


@router.get("/{image_id}/preview", summary="PNG preview of an original image or augmented sample (slice/window for volumes)",
            response_class=Response, responses={200: {"content": {"image/png": {}}}})
def preview(image_id: str, channel: int = Query(0, ge=0), slice_index: int | None = Query(None, ge=0), axis: int = Query(2, ge=0, le=2),
            window: str | None = Query(None, pattern="^(soft|lung|bone|auto)$"), max_size: int = Query(512, ge=32, le=1024), ctx=Depends(get_ctx)):
    png = preview_service.render_record(ctx, image_id, channel=channel, slice_index=slice_index, axis=axis, window=window, max_size=max_size)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})
