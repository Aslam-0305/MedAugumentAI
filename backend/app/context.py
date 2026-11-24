"""Application context: settings + store + storage + job executor, passed to services."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .db import FileStore, MongoStore
from .storage import Storage
from .utils.common import utcnow


@dataclass
class AppContext:
    settings: Settings
    store: FileStore | MongoStore
    storage: Storage
    executor: ThreadPoolExecutor
    cancel_events: dict[str, threading.Event] = field(default_factory=dict)

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.store.close()


def create_context(settings: Settings | None = None) -> AppContext:
    settings = settings or Settings.from_env()
    storage = Storage(settings.storage_root)
    if settings.db_backend == "mongo":
        store: FileStore | MongoStore = MongoStore(settings.mongo_uri, settings.mongo_db)
    elif settings.db_backend == "file":
        store = FileStore(storage.root / "metadata_db.json")
    else:
        raise RuntimeError(f"Unknown DB_BACKEND '{settings.db_backend}' (use 'mongo' or 'file')")
    ctx = AppContext(settings, store, storage, ThreadPoolExecutor(max_workers=settings.worker_threads, thread_name_prefix="medaugment"))
    _fail_interrupted_work(ctx)
    return ctx


def _fail_interrupted_work(ctx: AppContext) -> None:
    """Jobs run in this process, so anything still queued/running at startup was interrupted."""
    msg = "Interrupted by a server restart. Create a new job to retry."
    for coll in ("augmentation_jobs", "exports"):
        ctx.store.update_many(coll, {"status": {"$in": ["queued", "running"]}},
                              set={"status": "failed", "error": msg, "completed_at": utcnow()})
