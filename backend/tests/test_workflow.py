"""Ingestion validation, splits, end-to-end jobs and export (design §18.1, §18.3, §19)."""
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from app.services import analysis_service as an
from app.services import augmentation_service as au
from app.services import dataset_service as ds
from app.services import export_service as ex
from app.services import job_service as js
from app.services import split_service as sp
from app.utils.common import AppError
from tests.helpers import ingest, new_ctx, wait_export, wait_job, zip_bytes


def _png(v=100, size=(40, 40), seed=0):
    a = np.full(size, v, np.uint8); a[10:30, 10:30] = (v + 80) % 255; a += np.random.default_rng(seed).integers(0, 10, size).astype(np.uint8)
    b = io.BytesIO(); Image.fromarray(a).save(b, format="PNG"); return b.getvalue()


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- ingestion
def test_manifest_labels_map_to_images_and_pseudonymise():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "xray")
    assert d["status"] == "ready" and d["classes"] == ["normal", "pneumonia", "tuberculosis"]
    imgs = ctx.store.find("images", {"dataset_id": d["dataset_id"]})
    assert all(i["source_ref"] for i in imgs)
    for i in imgs:  # filenames encode the true class in the generator -> verify label mapping
        assert Path(ctx.storage.path(i["file_path"])).name.startswith(i["labels"][0])
        assert i["patient_id"].startswith("S") and not i["patient_id"].startswith("P0")
    assert "pseudonym_salt" not in d


def test_folder_per_class_layout():
    ctx, tmp = new_ctx()
    z = zip_bytes({"Normal/a.png": _png(50, seed=1), "Normal/b.png": _png(60, seed=2), "Pneumonia/c.png": _png(90, seed=3)}, tmp / "f.zip")
    d = ds.create_dataset(ctx, name="f", modality="xray", layout="folders", archives=[z], loose_files=[], manifest=None)
    assert d["classes"] == ["Normal", "Pneumonia"] and d["annotation_type"] == "single" and d["counts"]["valid"] == 3
    assert {tuple(i["labels"]) for i in ctx.store.find("images", {"dataset_id": d["dataset_id"]})} == {("Normal",), ("Pneumonia",)}


def test_validation_reports_missing_corrupt_duplicate_and_unlabelled():
    ctx, tmp = new_ctx()
    manifest = "image_path,patient_id,label\nok1.png,P1,a\nok2.png,P2,b\nmissing.png,P3,a\nbroken.png,P4,a\nok1.png,P1,a\nok3.png,P5,\n"
    z = zip_bytes({"manifest.csv": manifest.encode(), "ok1.png": _png(40, seed=1), "ok2.png": _png(80, seed=2), "ok3.png": _png(120, seed=3), "broken.png": b"not an image"}, tmp / "v.zip")
    d = ds.create_dataset(ctx, name="v", modality="xray", layout="manifest", archives=[z], loose_files=[], manifest=None)
    codes = d["validation"]["by_code"]
    assert d["status"] == "ready_with_issues" and d["counts"] == {"total": 6, "valid": 2, "invalid": 4, "patients": 2}
    assert codes["missing_file"] == 1 and codes["unreadable"] == 1 and codes["duplicate_path"] == 1 and codes["missing_label"] == 1
    assert an.dataset_statistics(ctx, d["dataset_id"], "all")["n_images"] == 2   # invalid images are excluded from analysis


def test_modality_mismatch_is_flagged():
    ctx, tmp = new_ctx()
    from scripts.make_sample_data import make_dataset
    z = make_dataset("ct", tmp / "d")
    d = ds.create_dataset(ctx, name="x", modality="xray", layout="manifest", archives=[z], loose_files=[], manifest=None)
    assert d["status"] == "failed" and d["validation"]["by_code"].get("unreadable", 0) + d["validation"]["by_code"].get("dimension_mismatch", 0) > 0


def test_archive_safety_guards():
    ctx, tmp = new_ctx()
    z = zip_bytes({"manifest.csv": b"image_path,label\n../evil.png,a\n", "../escape.txt": b"x"}, tmp / "bad.zip")
    try:
        ds.create_dataset(ctx, name="bad", modality="xray", layout="manifest", archives=[z], loose_files=[], manifest=None)
        raise AssertionError("zip-slip archive accepted")
    except AppError as e:
        assert e.code == "unsafe_archive"
    assert not (tmp / "escape.txt").exists() and not (tmp / "storage" / "escape.txt").exists()
    assert ds.list_datasets(ctx) == [], "failed upload must leave no dataset behind"


def test_multilabel_detection_and_cooccurrence():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "xray", multilabel=True)
    st = an.dataset_statistics(ctx, d["dataset_id"], "all")
    assert d["annotation_type"] == "multilabel" and st["cooccurrence"]["matrix"][1][2] == 8   # pneumonia & tuberculosis
    assert st["label_cardinality"] > 1.0


# ---------------------------------------------------------------- splits / leakage
def test_patient_level_split_has_no_leakage():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "xray")
    out = sp.create_splits(ctx, d["dataset_id"], seed=11)
    imgs = ctx.store.find("images", {"dataset_id": d["dataset_id"]})
    by_patient = {}
    for i in imgs:
        by_patient.setdefault(i["patient_id"], set()).add(i["split"])
    assert all(len(s) == 1 for s in by_patient.values()) and sum(v["images"] for v in out["summary"].values()) == len(imgs)
    assert out == sp.create_splits(ctx, d["dataset_id"], seed=11)  # same seed -> same split (compare incl. summary)


def test_split_rejects_supplied_splits_that_leak():
    ctx, tmp = new_ctx()
    m = "image_path,patient_id,label,split\na.png,P1,x,train\nb.png,P1,x,test\nc.png,P2,x,train\n"
    z = zip_bytes({"manifest.csv": m.encode(), "a.png": _png(1, seed=1), "b.png": _png(60, seed=2), "c.png": _png(120, seed=3)}, tmp / "s.zip")
    d = ds.create_dataset(ctx, name="s", modality="xray", layout="manifest", archives=[z], loose_files=[], manifest=None)
    assert d["validation"]["by_code"]["patient_split_conflict"] == 1
    try:
        sp.create_splits(ctx, d["dataset_id"], mode="use_existing")
        raise AssertionError("leaky supplied split accepted")
    except AppError as e:
        assert e.code == "patient_split_conflict"


# ---------------------------------------------------------------- end to end
BAL = {"strategy": "balance_largest", "max_expansion_factor": 6}


def _run(ctx, d, seed=7, aug=None, bal=BAL):
    job = au.create_job(ctx, d["dataset_id"], bal, aug, seed=seed)
    return wait_job(ctx, job["job_id"])


def test_all_modalities_end_to_end_with_provenance_and_unchanged_originals():
    for modality in ("xray", "ct", "mri"):
        ctx, tmp = new_ctx()
        d = ingest(ctx, tmp, modality)
        sp.create_splits(ctx, d["dataset_id"], seed=1)
        imgs = {i["image_id"]: i for i in ctx.store.find("images", {"dataset_id": d["dataset_id"]})}
        before = {k: _sha(ctx.storage.path(v["file_path"])) for k, v in imgs.items()}
        plan = au.build_plan(ctx, d["dataset_id"], BAL, None)
        job = _run(ctx, d)
        assert job["status"] == "completed", (modality, job.get("error"))
        samples = ctx.store.find("augmented_samples", {"job_id": job["job_id"]})
        assert len(samples) == plan["total_additional"] == job["progress"]["total"]
        for s in samples:
            src = imgs[s["source_image_id"]]
            assert s["labels"] == src["labels"] and src["split"] == "train" and s["patient_id"] == src["patient_id"]  # lineage + train-only
            assert s["transform_history"] and s["seed"]["job_seed"] == 7
            assert s["validation_status"] != "rejected" and ctx.storage.path(s["output_path"]).is_file()
            assert (ctx.storage.augmented_dir(job["job_id"]) / "provenance" / f"{s['sample_id']}.json").is_file()
        after = {k: _sha(ctx.storage.path(v["file_path"])) for k, v in imgs.items()}
        assert before == after, "original files were modified"
        r = js.job_results(ctx, job["job_id"])
        assert all(c["final"] >= c["original"] for c in r["classes"])


def test_geometry_and_mask_preserved_for_volumes():
    from app.imaging.loaders import load_image
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "mri")
    job = _run(ctx, d, bal={"strategy": "balance_largest", "max_expansion_factor": 10})
    s = next(s for s in ctx.store.find("augmented_samples", {"job_id": job["job_id"]}) if s.get("mask_path"))
    src = ctx.store.find_one("images", {"image_id": s["source_image_id"]})
    a, b = load_image(ctx.storage.path(src["file_paths"][0]), "mri"), load_image(ctx.storage.path(s["output_path"]), "mri")
    m = load_image(ctx.storage.path(s["mask_path"]), "mri")
    assert a.array.shape == b.array.shape == (3, 40, 40, 20) and np.allclose(a.affine, b.affine) and m.array.shape == (40, 40, 20)
    assert m.array.sum() > 0


def test_same_seed_reproduces_identical_files():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "xray")
    a, b = _run(ctx, d, seed=99), _run(ctx, d, seed=99)
    c = _run(ctx, d, seed=100)
    def digest(j):
        return [s["sha256"] for s in ctx.store.find("augmented_samples", {"job_id": j["job_id"]}, sort=[("sample_id", 1)])]
    assert digest(a) == digest(b) and digest(a) != digest(c)


def test_plan_respects_limits_and_blocks_invalid_requests():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "xray")
    p = au.build_plan(ctx, d["dataset_id"], {"strategy": "target_count", "target_count": 1000, "max_expansion_factor": 2}, None)
    assert all(c["projected"] <= 2 * c["original"] for c in p["classes"]) and any("splits" in w for w in p["warnings"])
    for bad in ({"strategy": "bogus"}, {"strategy": "target_count"}):
        try:
            au.build_plan(ctx, d["dataset_id"], bad, None); raise AssertionError(bad)
        except AppError as e:
            assert e.status == 400
    try:
        au.create_job(ctx, d["dataset_id"], {"strategy": "target_count", "target_count": 1}, None)
        raise AssertionError("empty plan accepted")
    except AppError as e:
        assert e.code == "nothing_to_do"


def test_cancel_queued_and_running_jobs():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "ct", scale=3)
    ctx.executor.submit(lambda: __import__("time").sleep(1.5))  # occupy workers so the next jobs queue
    ctx.executor.submit(lambda: __import__("time").sleep(1.5))
    job = au.create_job(ctx, d["dataset_id"], BAL, None, seed=1)
    assert js.cancel_job(ctx, job["job_id"])["status"] == "cancelled"
    assert wait_job(ctx, job["job_id"])["status"] == "cancelled"
    assert ctx.store.count("augmented_samples", {"job_id": job["job_id"]}) == 0
    try:
        js.cancel_job(ctx, job["job_id"]); raise AssertionError
    except AppError as e:
        assert e.status == 409


def test_rejected_samples_are_excluded_from_export_and_manual_review_works():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "xray")
    sp.create_splits(ctx, d["dataset_id"], seed=2)
    job = _run(ctx, d)
    samples = ctx.store.find("augmented_samples", {"job_id": job["job_id"]}, sort=[("sample_id", 1)])
    js.review_sample(ctx, job["job_id"], samples[0]["sample_id"], "rejected")
    e = wait_export(ctx, ex.create_export(ctx, job["job_id"])["export_id"])
    assert e["status"] == "completed" and e["report"]["samples"]["rejected_by_user"] == 1
    with zipfile.ZipFile(ctx.storage.path(e["archive_path"])) as zf:
        assert not any(samples[0]["sample_id"] in n for n in zf.namelist())


def test_export_is_self_describing_verifiable_and_private():
    ctx, tmp = new_ctx()
    d = ingest(ctx, tmp, "xray")
    sp.create_splits(ctx, d["dataset_id"], seed=2)
    job = _run(ctx, d)
    e = wait_export(ctx, ex.create_export(ctx, job["job_id"])["export_id"])
    assert e["status"] == "completed", e["error"]
    imgs = {i["image_id"]: i for i in ctx.store.find("images", {"dataset_id": d["dataset_id"]})}
    with zipfile.ZipFile(ctx.storage.path(e["archive_path"])) as zf:
        root = zf.namelist()[0].split("/")[0]
        rows = list(csv.DictReader(io.StringIO(zf.read(f"{root}/manifest.csv").decode())))
        assert len(rows) == len(imgs) + job["progress"]["accepted"] + job["progress"]["warnings"]
        for r in rows:
            data = zf.read(f"{root}/{r['file_path']}")
            assert hashlib.sha256(data).hexdigest() == r["sha256"]                 # reload + verify
            assert Image.open(io.BytesIO(data)).size == (128, 128)
            assert r["labels"] and all(r[c] in ("0", "1") for c in d["classes"])
            if r["split"] in ("val", "test"):                                        # held-out data: unchanged originals
                assert r["is_augmented"] == "0" and r["sha256"] == _sha(ctx.storage.path(imgs[r["image_id"]]["file_path"]))
            if r["is_augmented"] == "1":
                assert r["source_image_id"] in imgs and imgs[r["source_image_id"]]["split"] == "train" and json.loads(r["transform_history"])
        blob = b"".join(zf.read(n) for n in zf.namelist() if n.endswith((".csv", ".json", ".jsonl", ".md", ".txt")))
        assert b"P0001" not in blob and b"images/normal_" not in blob          # raw patient ids / upload filenames never exported
        rep = json.loads(zf.read(f"{root}/summary_report.json"))
        assert rep["before_counts_train"] and rep["generated_counts"] and "disclaimer" in rep


def test_loose_file_upload_with_separate_manifest():
    ctx, tmp = new_ctx()
    (tmp / "u").mkdir()
    files = []
    for n, (name, seed, v) in enumerate([("imgs/a.png", 1, 40), ("imgs/b.png", 2, 90)]):
        p = tmp / "u" / f"f{n}"; p.write_bytes(_png(v, seed=seed)); files.append((name, p))
    man = tmp / "u" / "m.csv"; man.write_text("image_path,label\nimgs/a.png,x\nimgs/b.png,y\n")
    d = ds.create_dataset(ctx, name="loose", modality="xray", layout="manifest", archives=[], loose_files=files, manifest=man)
    assert d["status"] == "ready" and d["classes"] == ["x", "y"]
    try:
        ds.create_dataset(ctx, name="evil", modality="xray", layout="manifest", archives=[], loose_files=[("../../x.png", files[0][1])], manifest=man)
        raise AssertionError("path traversal in loose filename accepted")
    except AppError as e:
        assert e.code == "unsafe_path"


def test_excel_manifest_and_multiclass_sheets():
    import openpyxl
    ctx, tmp = new_ctx()
    # Create Normal.xlsx
    wb1 = openpyxl.Workbook()
    ws1 = wb1.active
    ws1.append(["image_path", "patient_id"])
    ws1.append(["images/norm1.png", "P01"])
    ws1.append(["images/norm2.png", "P02"])
    p1 = tmp / "Normal.xlsx"
    wb1.save(p1)

    # Create Rare.xlsx
    wb2 = openpyxl.Workbook()
    ws2 = wb2.active
    ws2.append(["image_path", "patient_id"])
    ws2.append(["images/rare1.png", "P03"])
    p2 = tmp / "Rare.xlsx"
    wb2.save(p2)

    # Zip images + both Excel manifests together
    z = zip_bytes({
        "Normal.xlsx": p1.read_bytes(),
        "Rare.xlsx": p2.read_bytes(),
        "images/norm1.png": _png(50, seed=1),
        "images/norm2.png": _png(60, seed=2),
        "images/rare1.png": _png(70, seed=3),
    }, tmp / "excel_dataset.zip")

    d = ds.create_dataset(ctx, name="excel_test", modality="xray", layout="manifest", archives=[z], loose_files=[], manifest=None)
    assert d["status"] == "ready"
    assert d["classes"] == ["Normal", "Rare"]
    assert d["counts"]["valid"] == 3
    assert d["counts"]["patients"] == 3

