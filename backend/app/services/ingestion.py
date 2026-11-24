"""Ingestion layer: safe archive extraction and annotation parsing (design §4)."""
from __future__ import annotations

import csv
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..config import Settings
from ..imaging.loaders import detect_format
from ..utils.common import AppError

RESERVED = {"image_path", "path", "file", "filename", "image", "patient_id", "subject_id", "patient", "split", "mask_path", "mask",
            "modality", "label", "class", "labels"}
PATH_COLS = ("image_path", "path", "file", "filename", "image")
PATIENT_COLS = ("patient_id", "subject_id", "patient")
JUNK = {".ds_store", "thumbs.db"}


def issue(level: str, code: str, message: str, ref: str | None = None) -> dict:
    return {"level": level, "code": code, "message": message, "ref": ref}


# ------------------------------------------------------------------ archives
def safe_extract_zip(zip_path: Path, dest: Path, settings: Settings) -> int:
    """Extract with zip-slip, symlink, file-count, size and compression-ratio guards. Returns file count."""
    dest = Path(dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    limit = settings.max_uncompressed_mb * 1024 * 1024
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise AppError("The uploaded archive is not a valid ZIP file", 400, "bad_archive") from exc
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > settings.max_archive_files:
            raise AppError(f"Archive contains {len(infos)} files (limit {settings.max_archive_files})", 400, "archive_too_large")
        declared, packed = sum(i.file_size for i in infos), sum(i.compress_size for i in infos)
        if declared > limit:
            raise AppError(f"Archive expands to {declared // 2**20} MB (limit {settings.max_uncompressed_mb} MB)", 400, "archive_too_large")
        if packed and declared / packed > settings.max_archive_ratio and declared > 50 * 2**20:
            raise AppError("Archive compression ratio is suspiciously high (possible zip bomb)", 400, "archive_suspicious")
        written, count = 0, 0
        for info in infos:
            name = PurePosixPath(info.filename.replace("\\", "/"))
            if name.is_absolute() or ".." in name.parts or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise AppError(f"Unsafe path in archive: {info.filename}", 400, "unsafe_archive")
            if name.name.lower() in JUNK or "__MACOSX" in name.parts or name.name.startswith("._"):
                continue
            target = (dest / Path(*name.parts)).resolve()
            if dest not in target.parents:
                raise AppError(f"Unsafe path in archive: {info.filename}", 400, "unsafe_archive")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:  # stream with a running size check (headers can lie)
                while chunk := src.read(1 << 20):
                    written += len(chunk)
                    if written > limit:
                        raise AppError("Archive exceeds the uncompressed size limit while extracting", 400, "archive_too_large")
                    out.write(chunk)
            count += 1
    return count


def sanitize_relpath(filename: str) -> Path:
    name = PurePosixPath(filename.replace("\\", "/"))
    parts = [p for p in name.parts if p not in ("", ".", "/")]
    if not parts or ".." in parts:
        raise AppError(f"Unsafe file name: {filename}", 400, "unsafe_path")
    return Path(*parts)


# ------------------------------------------------------------------ file index
class FileIndex:
    """Resolve manifest paths against the extracted files, tolerating a wrapper directory."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        self.dirs = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir()}
        self.by_base: dict[str, list[str]] = {}
        for f in self.files:
            self.by_base.setdefault(PurePosixPath(f).name, []).append(f)
        tops = {PurePosixPath(f).parts[0] for f in self.files if len(PurePosixPath(f).parts) > 1}
        top_files = [f for f in self.files if len(PurePosixPath(f).parts) == 1]
        self.wrapper = next(iter(tops)) if len(tops) == 1 and not top_files else None

    def resolve(self, rel: str) -> Path | None:
        rel = PurePosixPath(rel.replace("\\", "/")).as_posix().lstrip("/")
        if ".." in PurePosixPath(rel).parts:
            return None
        cands = [rel] + ([f"{self.wrapper}/{rel}"] if self.wrapper else [])
        for c in cands:
            if c in self.files or c in self.dirs:
                return self.root / c
        matches = self.by_base.get(PurePosixPath(rel).name, [])
        return self.root / matches[0] if len(matches) == 1 else None


# ------------------------------------------------------------------ annotations
@dataclass
class Record:
    row: int
    paths: list[str]
    labels: list[str]
    raw_patient: str | None = None
    mask: str | None = None
    split: str | None = None
    resolved: list[Path] = field(default_factory=list)


@dataclass
class Parsed:
    records: list[Record]
    classes: list[str]
    annotation_type: str  # single | multilabel
    issues: list[dict]


_TRUE, _FALSE = {"1", "true", "yes", "y", "t"}, {"0", "false", "no", "n", "f", ""}
_SPLITS = {"train": "train", "training": "train", "val": "val", "valid": "val", "validation": "val", "test": "test", "testing": "test"}


def normalise_split(value: str | None) -> str | None:
    return _SPLITS.get((value or "").strip().lower())


def parse_manifest(csv_path: Path) -> Parsed:
    issues: list[dict] = []
    try:
        text = Path(csv_path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("The manifest must be UTF-8 encoded CSV text", 400, "bad_manifest") from exc
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise AppError("The manifest CSV is empty", 400, "bad_manifest")
    cols = {c.strip(): c for c in reader.fieldnames if c and c.strip()}
    lower = {c.lower(): c for c in cols}
    path_col = next((cols[lower[c]] for c in PATH_COLS if c in lower), None)
    if path_col is None:
        raise AppError(f"The manifest needs an image path column (one of: {', '.join(PATH_COLS)})", 400, "bad_manifest")
    pat_col = next((cols[lower[c]] for c in PATIENT_COLS if c in lower), None)
    split_col, mask_col = (cols[lower[c]] if c in lower else None for c in ("split", "mask_path"))
    mask_col = mask_col or (cols[lower["mask"]] if "mask" in lower else None)
    single_col = next((cols[lower[c]] for c in ("label", "class") if c in lower), None)
    multi_col = cols[lower["labels"]] if "labels" in lower else None
    rows = list(reader)
    if not rows:
        raise AppError("The manifest has no rows", 400, "bad_manifest")

    label_cols: list[str] = []
    if not (single_col or multi_col):
        for col in (c for c in reader.fieldnames if c and c.strip().lower() not in RESERVED):
            vals = {(r.get(col) or "").strip().lower() for r in rows}
            if vals <= (_TRUE | _FALSE):
                label_cols.append(col)
            else:
                issues.append(issue("warning", "column_ignored", f"Column '{col}' is not binary (0/1) and was ignored", col))
        if not label_cols:
            raise AppError("No label information found. Provide a 'label' column, a 'labels' column (separated by |), or binary 0/1 columns per class", 400, "bad_manifest")

    records: list[Record] = []
    for n, r in enumerate(rows, start=2):  # row 1 is the header
        raw_paths = [p.strip() for p in (r.get(path_col) or "").split(";") if p.strip()]
        if single_col:
            labels = [x.strip() for x in (r.get(single_col) or "").split("|") if x.strip()]
        elif multi_col:
            labels = [x.strip() for x in (r.get(multi_col) or "").split("|") if x.strip()]
        else:
            labels = [c.strip() for c in label_cols if (r.get(c) or "").strip().lower() in _TRUE]
        records.append(Record(n, raw_paths, labels, ((r.get(pat_col) or "").strip() or None) if pat_col else None,
                              ((r.get(mask_col) or "").strip() or None) if mask_col else None,
                              normalise_split(r.get(split_col)) if split_col else None))
        if split_col and r.get(split_col, "").strip() and normalise_split(r.get(split_col)) is None:
            issues.append(issue("warning", "unknown_split", f"Row {n}: unrecognised split '{r.get(split_col)}' (use train/val/test)", f"row {n}"))
    classes = sorted({l for rec in records for l in rec.labels}) if not label_cols else [c.strip() for c in label_cols]
    multilabel = bool(multi_col) or any(len(rec.labels) > 1 for rec in records)
    return Parsed(records, classes, "multilabel" if multilabel else "single", issues)


def parse_folders(root: Path, index: FileIndex) -> Parsed:
    base = root / index.wrapper if index.wrapper else root
    issues: list[dict] = []
    records: list[Record] = []
    classes: list[str] = []
    for cls_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        classes.append(cls_dir.name)
        for item in sorted(cls_dir.iterdir()):
            if item.name.lower() in JUNK:
                continue
            fmt = detect_format(item)
            if fmt is None:
                if item.is_file():
                    issues.append(issue("warning", "unsupported_file", f"Ignored unsupported file {item.name}", item.name))
                continue
            rec = Record(len(records) + 1, [item.relative_to(root).as_posix()], [cls_dir.name])
            rec.resolved = [item]
            records.append(rec)
    stray = [p.name for p in base.iterdir() if p.is_file() and p.name.lower() not in JUNK]
    if stray:
        issues.append(issue("warning", "stray_files", f"{len(stray)} file(s) outside class folders were ignored (e.g. {stray[0]})"))
    if not records:
        raise AppError("No images found. Folder layout must be <class>/<image files or DICOM series folders>", 400, "bad_dataset")
    return Parsed(records, [c for c in classes if any(c in r.labels for r in records)] or classes, "single", issues)


def clean_workdir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
