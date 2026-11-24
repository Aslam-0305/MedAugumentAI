"""Small shared helpers (ids, hashing, JSON-safe conversion, deterministic seeds)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def stable_entropy(*parts: Any) -> list[int]:
    """Map arbitrary parts to 32-bit ints usable by numpy SeedSequence.

    Python's built-in hash() is salted per process, so we use SHA-256 to keep
    random streams reproducible across runs and machines.
    """
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return [int.from_bytes(digest[i : i + 4], "little") for i in range(0, 16, 4)]


def to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays/tuples/paths into JSON-safe values."""
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, np.generic):
        return to_jsonable(obj.item())
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        return None
    return obj


class AppError(Exception):
    """Domain error carrying an HTTP-friendly status code."""

    def __init__(self, message: str, status: int = 400, code: str = "bad_request", details: Any = None):
        super().__init__(message)
        self.message, self.status, self.code, self.details = message, status, code, details


def not_found(what: str, ident: str) -> AppError:
    return AppError(f"{what} '{ident}' was not found", 404, "not_found")
