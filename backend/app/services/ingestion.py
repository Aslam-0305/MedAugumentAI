"""Ingestion layer: safe archive extraction and annotation parsing (design §4)."""
from __future__ import annotations

import csv
import io
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..config import Settings
from ..imaging.loaders import detect_format
from ..utils.common import AppError

RESERVED = {"image_path", "image_index", "image index", "image_name", "image name", "image_file", "imagefile", "path", "file", "filename", "file_name", "file name", "image", "filepath", "file_path",
            "patient_id", "patient id", "patientid", "subject_id", "subject id", "subject", "patient", "case_id", "case id", "case", "split", "mask_path", "mask",
            "modality", "label", "class", "labels", "diagnosis", "finding", "condition", "format", "size", "url"}
PATH_COLS = ("image_path", "image_index", "image index", "image_name", "image name", "image_file", "imagefile", "path", "file", "filename", "file_name", "file name", "image", "filepath", "file_path")
PATIENT_COLS = ("patient_id", "patient id", "patientid", "subject_id", "subject id", "subject", "patient", "case_id", "case id", "case")
SINGLE_LABEL_COLS = ("label", "class", "diagnosis", "finding", "condition")
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
        self.by_stem: dict[str, list[str]] = {}
        for f in self.files:
            p = PurePosixPath(f)
            self.by_base.setdefault(p.name.lower(), []).append(f)
            self.by_stem.setdefault(p.stem.lower(), []).append(f)
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

        # Case-insensitive base match (e.g. covid-1.png -> COVID/images/COVID-1.png)
        rel_base = PurePosixPath(rel).name.lower()
        base_matches = self.by_base.get(rel_base, [])
        if len(base_matches) == 1:
            return self.root / base_matches[0]
        elif len(base_matches) > 1:
            non_masks = [m for m in base_matches if "mask" not in m.lower()]
            if non_masks:
                return self.root / non_masks[0]
            return self.root / base_matches[0]

        # Case-insensitive stem match (e.g. 'COVID-1' -> 'COVID/images/COVID-1.png')
        rel_stem = PurePosixPath(rel).stem.lower()
        stem_matches = self.by_stem.get(rel_stem, [])
        if len(stem_matches) == 1:
            return self.root / stem_matches[0]
        elif len(stem_matches) > 1:
            non_masks = [m for m in stem_matches if "mask" not in m.lower()]
            if non_masks:
                return self.root / non_masks[0]
            return self.root / stem_matches[0]
        return None


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


def read_tabular_file(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Reads a CSV or Excel (.xlsx / .xls) file into a list of row dicts and header list."""
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            sheet = wb.active
            rows_iter = sheet.iter_rows(values_only=True)
            headers: list[str] | None = None
            for r in rows_iter:
                if any(v is not None and str(v).strip() for v in r):
                    headers = [str(v).strip() if v is not None else "" for v in r]
                    break
            if not headers:
                wb.close()
                return [], []
            data_rows = []
            for r in rows_iter:
                if not any(v is not None and str(v).strip() for v in r):
                    continue
                row_dict = {}
                for h, val in zip(headers, r):
                    if h:
                        row_dict[h] = "" if val is None else str(val).strip()
                data_rows.append(row_dict)
            wb.close()
            return headers, data_rows
        except Exception as exc:
            raise AppError(f"Failed to read Excel file {path.name}: {exc}", 400, "bad_manifest")
    else:
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="latin-1")
        reader = csv.DictReader(text.splitlines())
        fieldnames = [f.strip() for f in (reader.fieldnames or []) if f and f.strip()]
        return fieldnames, list(reader)


def parse_manifest(manifest_path: Path, default_label: str | None = None) -> Parsed:
    issues: list[dict] = []
    fieldnames, rows = read_tabular_file(manifest_path)
    if not fieldnames:
        raise AppError(f"The manifest spreadsheet ({manifest_path.name}) is empty", 400, "bad_manifest")
    cols = {c.strip(): c for c in fieldnames if c and c.strip()}
    lower = {c.lower(): c for c in cols}
    path_col = next((cols[lower[c]] for c in PATH_COLS if c in lower), None)
    if path_col is None:
        raise AppError(f"The manifest needs an image path column (found: {', '.join(fieldnames)})", 400, "bad_manifest")
    pat_col = next((cols[lower[c]] for c in PATIENT_COLS if c in lower), None)
    split_col, mask_col = (cols[lower[c]] if c in lower else None for c in ("split", "mask_path"))
    mask_col = mask_col or (cols[lower["mask"]] if "mask" in lower else None)
    single_col = next((cols[lower[c]] for c in SINGLE_LABEL_COLS if c in lower), None)
    multi_col = cols[lower["labels"]] if "labels" in lower else None
    if not rows:
        raise AppError(f"The manifest ({manifest_path.name}) has no data rows", 400, "bad_manifest")

    label_cols: list[str] = []
    has_explicit_labels = bool(single_col or multi_col)
    if not has_explicit_labels:
        for col in (c for c in fieldnames if c and c.strip().lower() not in RESERVED):
            vals = {(r.get(col) or "").strip().lower() for r in rows}
            if vals <= (_TRUE | _FALSE):
                label_cols.append(col)
            else:
                issues.append(issue("warning", "column_ignored", f"Column '{col}' is not binary (0/1) and was ignored", col))
        if label_cols:
            has_explicit_labels = True

    # If no explicit label columns exist but a default_label is provided (e.g. file is Normal.xlsx)
    if not has_explicit_labels and not default_label:
        raise AppError("No label information found. Provide a 'label' column, a 'labels' column, or binary 0/1 columns per class", 400, "bad_manifest")

    records: list[Record] = []
    for n, r in enumerate(rows, start=2):  # row 1 is the header
        raw_paths = [p.strip() for p in (r.get(path_col) or "").split(";") if p.strip()]
        if single_col:
            labels = [x.strip() for x in (r.get(single_col) or "").split("|") if x.strip()]
        elif multi_col:
            labels = [x.strip() for x in (r.get(multi_col) or "").split("|") if x.strip()]
        elif label_cols:
            labels = [c.strip() for c in label_cols if (r.get(c) or "").strip().lower() in _TRUE]
        else:
            labels = [default_label] if default_label else []

        records.append(Record(n, raw_paths, labels, ((r.get(pat_col) or "").strip() or None) if pat_col else None,
                              ((r.get(mask_col) or "").strip() or None) if mask_col else None,
                              normalise_split(r.get(split_col)) if split_col else None))
        if split_col and r.get(split_col, "").strip() and normalise_split(r.get(split_col)) is None:
            issues.append(issue("warning", "unknown_split", f"Row {n}: unrecognised split '{r.get(split_col)}' (use train/val/test)", f"row {n}"))

    if label_cols:
        classes = [c.strip() for c in label_cols]
    elif default_label and not has_explicit_labels:
        classes = [default_label]
    else:
        classes = sorted({l for rec in records for l in rec.labels})

    multilabel = bool(multi_col) or any(len(rec.labels) > 1 for rec in records)
    return Parsed(records, classes, "multilabel" if multilabel else "single", issues)


def parse_manifests(manifest_paths: list[Path]) -> tuple[Parsed, str]:
    """Parses one or multiple manifests (CSV or Excel) and compiles a unified manifest CSV."""
    if not manifest_paths:
        raise AppError("No manifest spreadsheet found (.csv, .xlsx, .xls)", 400, "bad_manifest")

    all_records: list[Record] = []
    all_issues: list[dict] = []
    all_classes: set[str] = set()
    is_multilabel = False

    for m_path in manifest_paths:
        # If multiple files exist, default label is the clean file stem (e.g. Normal.metadata.xlsx -> Normal, COVID.xlsx -> COVID)
        stem_clean = m_path.name.replace(".metadata", "").split(".")[0].strip()
        default_label = stem_clean if len(manifest_paths) > 1 else None
        parsed = parse_manifest(m_path, default_label=default_label)
        all_issues.extend(parsed.issues)
        all_classes.update(parsed.classes)
        if parsed.annotation_type == "multilabel":
            is_multilabel = True

        for rec in parsed.records:
            rec.row = len(all_records) + 2
            all_records.append(rec)

    # Build unified CSV string
    buf = io.StringIO()
    writer = csv.writer(buf)
    has_patient = any(r.raw_patient for r in all_records)
    has_split = any(r.split for r in all_records)
    has_mask = any(r.mask for r in all_records)

    header = ["image_path"]
    if has_patient:
        header.append("patient_id")
    header.append("label")
    if has_split:
        header.append("split")
    if has_mask:
        header.append("mask_path")
    writer.writerow(header)

    for rec in all_records:
        row = [";".join(rec.paths)]
        if has_patient:
            row.append(rec.raw_patient or "")
        row.append("|".join(rec.labels))
        if has_split:
            row.append(rec.split or "")
        if has_mask:
            row.append(rec.mask or "")
        writer.writerow(row)

    combined = Parsed(
        records=all_records,
        classes=sorted(all_classes),
        annotation_type="multilabel" if is_multilabel else "single",
        issues=all_issues,
    )
    return combined, buf.getvalue()


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
