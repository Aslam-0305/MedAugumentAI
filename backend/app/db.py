"""Metadata store abstraction.

`MongoStore` is the production backend (design section 13). `FileStore` is a
zero-dependency JSON-backed implementation with the same small query subset, used
for tests and for running the app without a MongoDB server (DB_BACKEND=file).

Supported filter operators: equality (list fields match by membership, as in
MongoDB), "$in", "$ne", "$nin". Services only use this subset so both backends
behave identically.
"""
from __future__ import annotations

import atexit
import copy
import json
import threading
import time
from pathlib import Path
from typing import Any, Iterable

COLLECTIONS = ("datasets", "images", "augmentation_jobs", "augmented_samples", "exports")


def _match(doc: dict, flt: dict | None) -> bool:
    for key, cond in (flt or {}).items():
        value = doc.get(key)
        if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                if op == "$in":
                    vals = value if isinstance(value, list) else [value]
                    if not any(v in arg for v in vals):
                        return False
                elif op == "$nin":
                    vals = value if isinstance(value, list) else [value]
                    if any(v in arg for v in vals):
                        return False
                elif op == "$ne":
                    if value == arg or (isinstance(value, list) and arg in value):
                        return False
                else:
                    raise ValueError(f"Unsupported operator {op}")
        elif isinstance(value, list) and not isinstance(cond, list):
            if cond not in value:
                return False
        elif value != cond:
            return False
    return True


def _sorted(docs: list[dict], sort: list[tuple[str, int]] | None) -> list[dict]:
    for key, direction in reversed(sort or []):
        docs.sort(key=lambda d: (d.get(key) is None, d.get(key)), reverse=direction < 0)
    return docs


class FileStore:
    def __init__(self, path: Path | None = None):
        self._path = Path(path) if path else None
        self._lock = threading.RLock()
        self._data: dict[str, list[dict]] = {c: [] for c in COLLECTIONS}
        self._dirty, self._last_flush = False, 0.0
        if self._path and self._path.is_file():
            loaded = json.loads(self._path.read_text())
            for name in COLLECTIONS:
                self._data[name] = loaded.get(name, [])
        atexit.register(self.flush)

    def flush(self, force: bool = True) -> None:
        with self._lock:
            if not self._path or not self._dirty:
                return
            if not force and time.time() - self._last_flush < 1.0:
                return
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data))
            tmp.replace(self._path)
            self._dirty, self._last_flush = False, time.time()

    def _touch(self) -> None:
        self._dirty = True
        self.flush(force=False)

    # -- writes ----------------------------------------------------------
    def insert_one(self, coll: str, doc: dict) -> None:
        self.insert_many(coll, [doc])

    def insert_many(self, coll: str, docs: Iterable[dict]) -> None:
        with self._lock:
            self._data[coll].extend(copy.deepcopy(list(docs)))
            self._touch()

    @staticmethod
    def _apply(doc: dict, set: dict | None, push: dict | None, push_cap: int, inc: dict | None) -> None:
        for k, v in (set or {}).items():
            doc[k] = copy.deepcopy(v)
        for k, v in (inc or {}).items():
            doc[k] = doc.get(k, 0) + v
        for k, v in (push or {}).items():
            arr = doc.setdefault(k, [])
            arr.append(copy.deepcopy(v))
            del arr[:-push_cap]

    def update_many(self, coll: str, flt: dict, set: dict | None = None, push: dict | None = None,
                    push_cap: int = 200, inc: dict | None = None) -> int:
        with self._lock:
            hits = [d for d in self._data[coll] if _match(d, flt)]
            for doc in hits:
                self._apply(doc, set, push, push_cap, inc)
            if hits:
                self._touch()
            return len(hits)

    def update_one(self, coll: str, flt: dict, set: dict | None = None, push: dict | None = None,
                   push_cap: int = 200, inc: dict | None = None) -> int:
        with self._lock:
            doc = next((d for d in self._data[coll] if _match(d, flt)), None)
            if doc is None:
                return 0
            self._apply(doc, set, push, push_cap, inc)
            self._touch()
            return 1

    def delete_many(self, coll: str, flt: dict) -> int:
        with self._lock:
            before = len(self._data[coll])
            self._data[coll] = [d for d in self._data[coll] if not _match(d, flt)]
            if len(self._data[coll]) != before:
                self._touch()
            return before - len(self._data[coll])

    # -- reads -----------------------------------------------------------
    def find(self, coll: str, flt: dict | None = None, *, sort: list[tuple[str, int]] | None = None,
             skip: int = 0, limit: int = 0, fields: list[str] | None = None) -> list[dict]:
        with self._lock:
            docs = [d for d in self._data[coll] if _match(d, flt)]
            docs = copy.deepcopy(_sorted(docs, sort))
        docs = docs[skip:] if not limit else docs[skip : skip + limit]
        if fields:
            docs = [{k: d[k] for k in fields if k in d} for d in docs]
        return docs

    def find_one(self, coll: str, flt: dict) -> dict | None:
        found = self.find(coll, flt, limit=1)
        return found[0] if found else None

    def count(self, coll: str, flt: dict | None = None) -> int:
        with self._lock:
            return sum(1 for d in self._data[coll] if _match(d, flt))

    def close(self) -> None:
        self.flush()


class MongoStore:
    def __init__(self, uri: str, db_name: str):
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pymongo is required for DB_BACKEND=mongo (pip install pymongo)") from exc
        self._client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        try:
            self._client.admin.command("ping")
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"Cannot reach MongoDB at {uri}. Start MongoDB (see docker-compose.yml) "
                "or set DB_BACKEND=file for a zero-dependency local store."
            ) from exc
        self._db = self._client[db_name]
        self._db["datasets"].create_index("dataset_id", unique=True)
        self._db["images"].create_index("image_id", unique=True)
        self._db["images"].create_index([("dataset_id", 1), ("split", 1)])
        self._db["augmentation_jobs"].create_index("job_id", unique=True)
        self._db["augmented_samples"].create_index("sample_id", unique=True)
        self._db["augmented_samples"].create_index([("job_id", 1), ("validation_status", 1)])
        self._db["exports"].create_index("export_id", unique=True)

    def insert_one(self, coll: str, doc: dict) -> None:
        self._db[coll].insert_one(dict(doc))

    def insert_many(self, coll: str, docs: Iterable[dict]) -> None:
        docs = [dict(d) for d in docs]
        if docs:
            self._db[coll].insert_many(docs)

    def update_many(self, coll: str, flt: dict, set: dict | None = None, push: dict | None = None,
                    push_cap: int = 200, inc: dict | None = None) -> int:
        update: dict[str, Any] = {}
        if set:
            update["$set"] = set
        if inc:
            update["$inc"] = inc
        if push:
            update["$push"] = {k: {"$each": [v], "$slice": -push_cap} for k, v in push.items()}
        return self._db[coll].update_many(flt, update).modified_count if update else 0

    def update_one(self, coll: str, flt: dict, set: dict | None = None, push: dict | None = None,
                   push_cap: int = 200, inc: dict | None = None) -> int:
        update: dict[str, Any] = {}
        if set:
            update["$set"] = set
        if inc:
            update["$inc"] = inc
        if push:
            update["$push"] = {k: {"$each": [v], "$slice": -push_cap} for k, v in push.items()}
        return self._db[coll].update_one(flt, update).matched_count if update else 0

    def delete_many(self, coll: str, flt: dict) -> int:
        return self._db[coll].delete_many(flt).deleted_count

    def find(self, coll: str, flt: dict | None = None, *, sort: list[tuple[str, int]] | None = None,
             skip: int = 0, limit: int = 0, fields: list[str] | None = None) -> list[dict]:
        projection = {k: 1 for k in fields} if fields else {}
        projection["_id"] = 0
        cur = self._db[coll].find(flt or {}, projection)
        if sort:
            cur = cur.sort(sort)
        if skip:
            cur = cur.skip(skip)
        if limit:
            cur = cur.limit(limit)
        return list(cur)

    def find_one(self, coll: str, flt: dict) -> dict | None:
        return self._db[coll].find_one(flt, {"_id": 0})

    def count(self, coll: str, flt: dict | None = None) -> int:
        return self._db[coll].count_documents(flt or {})

    def close(self) -> None:
        self._client.close()
