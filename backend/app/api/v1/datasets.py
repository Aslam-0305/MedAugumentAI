from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...services import analysis_service, dataset_service, split_service
from ...schemas.requests import SplitRequest
from ..deps import UploadSession, get_ctx

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", status_code=201, summary="Create a dataset from a ZIP (or loose files) plus optional CSV manifest")
def create_dataset(name: str = Form(...), modality: str = Form(...), layout: str = Form("manifest"),
                   files: list[UploadFile] = File(default=[]), manifest: UploadFile | None = File(None), ctx=Depends(get_ctx)):
    session = UploadSession(ctx)
    try:
        archives, loose = [], []
        for f in files:
            saved = session.save(f)
            filename = f.filename or saved.name
            if filename.lower().endswith(".zip"):
                archives.append(saved)
            else:
                loose.append((filename, saved))  # filename may carry a relative folder path
        man = session.save(manifest) if manifest is not None and manifest.filename else None
        return dataset_service.create_dataset(ctx, name=name, modality=modality, layout=layout, archives=archives, loose_files=loose, manifest=man)
    finally:
        session.close()


@router.get("")
def list_datasets(ctx=Depends(get_ctx)):
    return dataset_service.list_datasets(ctx)


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str, ctx=Depends(get_ctx)):
    return dataset_service.public_dataset(dataset_service.get_dataset(ctx, dataset_id))


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, ctx=Depends(get_ctx)):
    dataset_service.delete_dataset(ctx, dataset_id)


@router.get("/{dataset_id}/images")
def list_images(dataset_id: str, split: str | None = None, label: str | None = None, status: str | None = None,
                skip: int = 0, limit: int = 48, ctx=Depends(get_ctx)):
    return dataset_service.list_images(ctx, dataset_id, split=split, label=label, status=status, skip=skip, limit=limit)


@router.get("/{dataset_id}/statistics")
def statistics(dataset_id: str, scope: str = "auto", ctx=Depends(get_ctx)):
    return analysis_service.dataset_statistics(ctx, dataset_id, scope)


@router.post("/{dataset_id}/splits")
def create_splits(dataset_id: str, body: SplitRequest, ctx=Depends(get_ctx)):
    return split_service.create_splits(ctx, dataset_id, mode=body.mode, ratios=body.ratios, seed=body.seed)
