"""Runtime settings, read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Strip inline comments unless enclosed in quotes
        if not (value.startswith('"') or value.startswith("'")):
            value = value.split("#")[0].strip()
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    storage_root: Path
    db_backend: str = "mongo"  # "mongo" | "file" (file = zero-dependency dev/test store)
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "medaugment"
    api_key: str | None = None  # when set, every /api request must send X-API-Key
    max_upload_mb: int = 4096
    max_archive_files: int = 200_000
    max_uncompressed_mb: int = 32_768
    max_archive_ratio: float = 200.0  # zip-bomb guard: uncompressed / compressed
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    worker_threads: int = 2
    max_job_additional: int = 50_000  # hard ceiling on generated samples per job

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        env = os.environ.get
        return cls(
            storage_root=Path(env("STORAGE_ROOT", "../storage")).resolve(),
            db_backend=env("DB_BACKEND", "mongo").lower(),
            mongo_uri=env("MONGO_URI", "mongodb://localhost:27017"),
            mongo_db=env("MONGO_DB", "medaugment"),
            api_key=env("API_KEY") or None,
            max_upload_mb=int(env("MAX_UPLOAD_MB", "4096")),
            max_archive_files=int(env("MAX_ARCHIVE_FILES", "200000")),
            max_uncompressed_mb=int(env("MAX_UNCOMPRESSED_MB", "32768")),
            max_archive_ratio=float(env("MAX_ARCHIVE_RATIO", "200")),
            cors_origins=tuple(o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()),
            worker_threads=int(env("WORKER_THREADS", "2")),
            max_job_additional=int(env("MAX_JOB_ADDITIONAL", "50000")),
        )
