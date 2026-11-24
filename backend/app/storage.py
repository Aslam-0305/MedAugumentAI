"""Filesystem layout (see design section 13.1). Image binaries never go in MongoDB."""
from __future__ import annotations

from pathlib import Path

from .utils.common import AppError


class Storage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- layout -------------------------------------------------------
    def dataset_dir(self, dataset_id: str) -> Path:
        return self.root / "datasets" / dataset_id

    def original_dir(self, dataset_id: str) -> Path:
        return self.dataset_dir(dataset_id) / "original"

    def manifests_dir(self, dataset_id: str) -> Path:
        return self.dataset_dir(dataset_id) / "manifests"

    def metadata_dir(self, dataset_id: str) -> Path:
        return self.dataset_dir(dataset_id) / "metadata"

    def processed_dir(self, dataset_id: str) -> Path:
        return self.root / "processed" / dataset_id

    def augmented_dir(self, job_id: str) -> Path:
        return self.root / "augmented" / job_id

    def export_dir(self, export_id: str) -> Path:
        return self.root / "exports" / export_id

    def tmp_dir(self) -> Path:
        p = self.root / "tmp"
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ---- keys <-> paths -------------------------------------------------
    def key(self, path: Path) -> str:
        """Storage key = path relative to the storage root (what we persist in the DB)."""
        return Path(path).resolve().relative_to(self.root).as_posix()

    def path(self, key: str) -> Path:
        return safe_join(self.root, key)


def safe_join(base: Path, rel: str) -> Path:
    """Join `rel` onto `base`, refusing anything that escapes `base` (path traversal guard)."""
    base = Path(base).resolve()
    target = (base / rel).resolve()
    if target != base and base not in target.parents:
        raise AppError("Path escapes the storage directory", 400, "unsafe_path")
    return target
