from __future__ import annotations

import tempfile
import time
import zipfile
from pathlib import Path

from app.config import Settings
from app.context import create_context
from app.services import dataset_service as ds
from app.services import export_service as ex
from app.services import job_service as js
from scripts.make_sample_data import make_dataset


def new_ctx():
    tmp = Path(tempfile.mkdtemp())
    return create_context(Settings(storage_root=tmp / "storage", db_backend="file")), tmp


def ingest(ctx, tmp, modality, **kw):
    z = make_dataset(modality, tmp / "data", **kw)
    return ds.create_dataset(ctx, name=modality, modality=modality, layout="manifest", archives=[z], loose_files=[], manifest=None)


def wait_job(ctx, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        j = js.get_job(ctx, job_id)
        if j["status"] in js.TERMINAL:
            return j
        time.sleep(0.05)
    raise TimeoutError(job_id)


def wait_export(ctx, export_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        e = ex.get_export(ctx, export_id)
        if e["status"] in ("completed", "failed"):
            return e
        time.sleep(0.05)
    raise TimeoutError(export_id)


def zip_bytes(files: dict[str, bytes], path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for k, v in files.items():
            zf.writestr(k, v)
    return path
