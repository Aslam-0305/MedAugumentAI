"""Generate small SYNTHETIC imbalanced datasets (X-ray / CT / MRI) for trying MedAugment AI.

These are procedurally drawn shapes, NOT real patient data and not clinically meaningful.

    python -m scripts.make_sample_data --modality xray --out ../sample_data
Creates <out>/<modality>_sample.zip containing images + manifest.csv.
"""
from __future__ import annotations

import argparse
import csv
import io
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from app.imaging.loaders.nifti_loader import save_nifti

CLASSES = {"xray": {"normal": 36, "pneumonia": 18, "tuberculosis": 8},
           "ct": {"normal": 20, "nodule": 9, "mass": 4},
           "mri": {"healthy": 16, "tumor": 7}}


def _xray(rng: np.random.Generator, label: str, size: int = 128) -> np.ndarray:
    yy, xx = np.mgrid[:size, :size] / size
    img = 0.15 + 0.1 * rng.random()
    body = np.exp(-(((xx - 0.5) / 0.42) ** 2 + ((yy - 0.5) / 0.48) ** 2) ** 2)
    lungs = sum(np.exp(-(((xx - cx) / 0.13) ** 2 + ((yy - 0.48) / 0.28) ** 2) ** 2) for cx in (0.34, 0.66))
    arr = img + 0.55 * body - 0.3 * lungs
    if label == "pneumonia":
        cx, cy = rng.uniform(0.25, 0.4), rng.uniform(0.5, 0.65)
        arr += 0.25 * np.exp(-(((xx - cx) / 0.08) ** 2 + ((yy - cy) / 0.1) ** 2))
    elif label == "tuberculosis":
        for _ in range(3):
            cx, cy = rng.uniform(0.55, 0.75), rng.uniform(0.3, 0.45)
            arr += 0.3 * np.exp(-(((xx - cx) / 0.03) ** 2 + ((yy - cy) / 0.03) ** 2))
    arr = ndi.gaussian_filter(arr, 1.0) + rng.normal(0, 0.015, arr.shape)
    return (np.clip(arr, 0, 1) * 255).astype(np.uint8)


def _ct(rng: np.random.Generator, label: str, shape=(48, 48, 24)) -> tuple[np.ndarray, None]:
    g = np.indices(shape).astype(float)
    cx, cy, cz = [(s - 1) / 2 for s in shape]
    body = (((g[0] - cx) / 20) ** 2 + ((g[1] - cy) / 16) ** 2) <= 1
    lungs = ((((g[0] - cx + 8) / 7) ** 2 + ((g[1] - cy) / 10) ** 2) <= 1) | ((((g[0] - cx - 8) / 7) ** 2 + ((g[1] - cy) / 10) ** 2) <= 1)
    z_ok = (g[2] > 3) & (g[2] < shape[2] - 4)
    vol = np.full(shape, -1000.0)
    vol[body & z_ok] = 40.0
    vol[lungs & z_ok] = -800.0
    r = {"normal": 0, "nodule": 2.5, "mass": 5.0}[label]
    if r:
        c = (cx + rng.choice([-8, 8]) + rng.normal(0, 1), cy + rng.normal(0, 2), cz + rng.normal(0, 1.5))
        vol[((g[0] - c[0]) ** 2 + (g[1] - c[1]) ** 2 + ((g[2] - c[2]) * 2.5 / 0.8) ** 2) <= r**2] = 30.0
    vol = ndi.gaussian_filter(vol, 0.6) + rng.normal(0, 8, shape)
    return np.clip(vol, -1024, 3000).astype(np.int16), None


def _mri(rng: np.random.Generator, label: str, shape=(40, 40, 20)):
    g = np.indices(shape).astype(float)
    c = [(s - 1) / 2 for s in shape]
    brain = (((g[0] - c[0]) / 16) ** 2 + ((g[1] - c[1]) / 14) ** 2 + ((g[2] - c[2]) / 8) ** 2) <= 1
    mask = np.zeros(shape, np.uint8)
    t1, t2, flair = brain * 0.6, brain * 0.5, brain * 0.55
    if label == "tumor":
        t = (rng.normal(c[0], 5), rng.normal(c[1], 5), rng.normal(c[2], 2))
        blob = ((g[0] - t[0]) ** 2 + (g[1] - t[1]) ** 2 + ((g[2] - t[2]) * 1.6) ** 2) <= rng.uniform(3, 5) ** 2
        blob &= brain
        mask[blob] = 1
        t1 = t1 - 0.2 * blob
        t2, flair = t2 + 0.4 * blob, flair + 0.5 * blob
    seq = [ndi.gaussian_filter(s, 0.7) + np.abs(rng.normal(0, 0.02, shape)) for s in (t1, t2, flair)]
    return np.stack(seq).astype(np.float32), mask


def make_dataset(modality: str, out_dir: Path, seed: int = 0, scale: float = 1.0, multilabel: bool = False) -> Path:
    rng = np.random.default_rng(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    buf_files: dict[str, bytes] = {}
    rows: list[dict] = []
    pid = 0
    for label, n in CLASSES[modality].items():
        for i in range(max(2, int(n * scale))):
            if i % 2 == 0:
                pid += 1  # every second image shares the previous patient
            patient = f"P{pid:04d}"
            name = f"images/{label}_{i:03d}"
            mask_name = ""
            if modality == "xray":
                bio = io.BytesIO()
                Image.fromarray(_xray(rng, label)).save(bio, format="PNG")
                buf_files[name + ".png"], rel = bio.getvalue(), name + ".png"
            else:
                arr, mask = (_ct if modality == "ct" else _mri)(rng, label)
                rel = name + ".nii.gz"
                tmp = out_dir / "_tmp.nii.gz"
                spacing = (0.8, 0.8, 2.5) if modality == "ct" else (1.0, 1.0, 1.5)
                aff = np.diag([*spacing, 1.0])
                save_nifti(tmp, arr, aff)
                buf_files[rel] = tmp.read_bytes()
                if mask is not None and mask.any():
                    mask_name = name + "_mask.nii.gz"
                    save_nifti(tmp, mask, aff)
                    buf_files[mask_name] = tmp.read_bytes()
                tmp.unlink()
            row = {"image_path": rel, "patient_id": patient, "label": label}
            if mask_name:
                row["mask_path"] = mask_name
            rows.append(row)
    if multilabel and modality == "xray":  # also tag some pneumonia images as having an additional finding
        classes = list(CLASSES[modality])
        for r in rows:
            r.update({c: int(r["label"] == c) for c in classes})
            if r["label"] == "tuberculosis":
                r["pneumonia"] = 1
            del r["label"]
    fields = list(dict.fromkeys(k for r in rows for k in r))
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=fields)
    w.writeheader()
    w.writerows({k: r.get(k, "") for k in fields} for r in rows)
    zip_path = out_dir / f"{modality}_sample{'_multilabel' if multilabel else ''}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.csv", sio.getvalue())
        for name, data in buf_files.items():
            zf.writestr(name, data)
    return zip_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modality", choices=list(CLASSES), default="xray")
    ap.add_argument("--out", default="../sample_data")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--multilabel", action="store_true")
    a = ap.parse_args()
    print(make_dataset(a.modality, Path(a.out), a.seed, a.scale, a.multilabel))
