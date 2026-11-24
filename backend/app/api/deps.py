from __future__ import annotations

import secrets
import shutil
import uuid
from pathlib import Path

from fastapi import Depends, Header, Request, UploadFile

from ..context import AppContext
from ..utils.common import AppError


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def require_api_key(ctx: AppContext = Depends(get_ctx), x_api_key: str | None = Header(None)) -> None:
    """Optional shared-secret auth (set API_KEY). Use real authentication/authorisation before multi-user deployment."""
    if ctx.settings.api_key and not (x_api_key and secrets.compare_digest(x_api_key, ctx.settings.api_key)):
        raise AppError("Missing or invalid API key", 401, "unauthorized")


class UploadSession:
    """Streams uploads to a temp dir with a cumulative size cap; always cleaned up."""

    def __init__(self, ctx: AppContext):
        self.ctx, self.dir, self.bytes = ctx, ctx.storage.tmp_dir() / f"upload_{uuid.uuid4().hex}", 0
        self.dir.mkdir(parents=True)

    def save(self, upload: UploadFile) -> Path:
        dest = self.dir / uuid.uuid4().hex
        limit = self.ctx.settings.max_upload_mb * 1024 * 1024
        with open(dest, "wb") as out:
            while chunk := upload.file.read(1 << 20):
                self.bytes += len(chunk)
                if self.bytes > limit:
                    raise AppError(f"Upload exceeds the {self.ctx.settings.max_upload_mb} MB limit", 413, "upload_too_large")
                out.write(chunk)
        return dest

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
