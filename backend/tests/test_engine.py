"""Loaders, transforms, modality policy, balancing (design §18.2, §7, §5)."""
import numpy as np

from app.imaging.adapters import get_adapter
from app.imaging.loaders import load_image, load_image_set
from app.imaging.loaders.image_2d import save_2d
from app.imaging.loaders.nifti_loader import load_nifti, save_nifti
from app.imaging.pipeline import AugmentationPipeline, parse_pipeline_config
from app.imaging.transforms.spatial import Resampler
from app.imaging.types import ImageData, orientation_codes
from app.imaging.validation import check_output
from app.services.balancing_service import BalancingConfig, compute_plan, projected_distribution
from app.utils.common import AppError
from tests.helpers import new_ctx


def test_png_and_nifti_roundtrip():
    _, tmp = new_ctx()
    for dt in (np.uint8, np.uint16):
        a = (np.random.default_rng(0).random((20, 30)) * 200).astype(dt)
        save_2d(tmp / "a.png", a)
        b = load_image(tmp / "a.png", "xray")
        assert b.array.dtype == dt and np.array_equal(a, b.array)
    aff = np.diag([0.7, 0.7, 2.5, 1.0]); aff[:3, 3] = [-10, 5, 30]
    v = (np.random.default_rng(1).random((12, 10, 8)) * 1000 - 500).astype(np.int16)
    save_nifti(tmp / "v.nii.gz", v, aff)
    r = load_nifti(tmp / "v.nii.gz", "ct")
    assert np.array_equal(r.array, v) and np.allclose(r.affine, aff) and r.source_dtype == "int16" and orientation_codes(r.affine) == "RAS"


def test_multisequence_must_be_aligned():
    _, tmp = new_ctx()
    v = np.zeros((8, 8, 4), np.float32)
    save_nifti(tmp / "a.nii.gz", v, np.eye(4))
    save_nifti(tmp / "b.nii.gz", v, np.diag([2, 2, 2, 1.0]))
    try:
        load_image_set([tmp / "a.nii.gz", tmp / "b.nii.gz"], "mri")
        raise AssertionError("misaligned sequences were accepted")
    except Exception as e:
        assert "aligned" in str(e)


def test_rotation_is_physical_not_voxel():
    """With 3 mm slices a physical sphere must stay a sphere (volume preserved) after 3-axis rotation."""
    sp, shape = (1.0, 1.0, 3.0), (41, 41, 15)
    g = np.indices(shape).astype(float)
    r2 = sum(((g[i] - (shape[i] - 1) / 2) * sp[i]) ** 2 for i in range(3))
    sphere = (r2 <= 100).astype(np.float32)
    out = Resampler(shape, sp, {"angles_deg": [30.0, 20.0, 10.0]}).apply(sphere, order=1, mode="constant", cval=0)
    assert abs(out.sum() / sphere.sum() - 1) < 0.03


def test_reproducible_and_mask_aligned():
    v = np.full((32, 32, 12), -1000, np.float32); v[6:26, 6:26, 2:10] = 40
    mk = np.zeros(v.shape, np.uint8); mk[12:20, 12:20, 4:8] = 1
    img = ImageData(v, "ct", 3, (1, 1, 2.5), affine=np.diag([1, 1, 2.5, 1.0]), mask=mk, source_dtype="int16")
    cfg, _ = parse_pipeline_config("ct", {"transforms": [{"name": "rotate", "probability": 1}, {"name": "translate", "probability": 1}, {"name": "hu_shift", "probability": 1}]})
    p = AugmentationPipeline(cfg)
    a, ha = p.run(img, np.random.default_rng(3)); b, hb = p.run(img, np.random.default_rng(3))
    assert np.array_equal(a.array, b.array) and np.array_equal(a.mask, b.mask) and ha == hb
    assert a.array.dtype == np.int16 and check_output(img, a, expected_dtype="int16")["status"] != "rejected"
    # the transformed mask must still sit on the bright object (same resampling applied)
    assert a.array[a.mask > 0].mean() > a.array[a.mask == 0].mean()
    assert np.array_equal(img.array, v), "source array must not be mutated"


def test_modality_policy_enforced():
    for modality, bad in (("ct", "gamma"), ("ct", "brightness_contrast"), ("mri", "hu_shift"), ("xray", "bias_field")):
        try:
            parse_pipeline_config(modality, {"transforms": [{"name": bad}]})
            raise AssertionError(f"{bad} allowed for {modality}")
        except AppError as e:
            assert e.code == "transform_not_allowed"
    try:
        parse_pipeline_config("xray", {"transforms": [{"name": "flip"}]})
        raise AssertionError("flip allowed without opt-in")
    except AppError as e:
        assert e.code == "laterality_flip_blocked"
    cfg, warns = parse_pipeline_config("xray", {"transforms": [{"name": "rotate", "params": {"max_degrees": 90}}]})
    assert cfg.transforms[0].params["max_degrees"] == 15 and warns
    codes = {i["code"] for i in get_adapter("mri").validate_input(ImageData(np.random.default_rng(0).random((8, 8)).astype(np.float32), "mri", 2, (1, 1)))}
    assert "dimension_mismatch" in codes


def test_validator_rejects_bad_outputs():
    src = ImageData(np.random.default_rng(0).integers(0, 255, (40, 40)).astype(np.uint8), "xray", 2, (1, 1))
    nan = src.replace(array=np.full((40, 40), np.nan, np.float32))
    blank = src.replace(array=np.zeros((40, 40), np.uint8))
    assert check_output(src, nan)["status"] == "rejected"
    assert check_output(src, blank)["status"] == "rejected"
    assert check_output(src, src.replace())["status"] == "warning"  # identical -> "no effective change"


def _samples(spec):
    return [{"image_id": f"{c}{i}", "labels": [c]} for c, n in spec for i in range(n)]


def test_balancing_matches_design_example():
    s = _samples([("Normal", 100), ("Pneumonia", 50), ("Tuberculosis", 20), ("Other", 10)])
    p = compute_plan(s, ["Normal", "Pneumonia", "Tuberculosis", "Other"], False, BalancingConfig(strategy="balance_largest"))
    assert {r["label"]: r["additional"] for r in p["classes"]} == {"Normal": 0, "Other": 90, "Pneumonia": 50, "Tuberculosis": 80}
    assert sum(a["n_variants"] for a in p["assignments"]) == p["total_additional"] == 220


def test_balancing_caps_exclusions_and_determinism():
    s = _samples([("a", 100), ("b", 10), ("c", 20)])
    cfg = BalancingConfig(max_expansion_factor=3, seed=5)
    p = compute_plan(s, list("abc"), False, cfg)
    by = {r["label"]: r for r in p["classes"]}
    assert by["b"]["projected"] == 30 and by["b"]["capped_by"] == "max_expansion_factor" and by["c"]["projected"] == 60
    assert p == compute_plan(s, list("abc"), False, cfg)
    p = compute_plan(s, list("abc"), False, BalancingConfig(excluded_classes=["b"]))
    assert {r["label"]: r["additional"] for r in p["classes"]}["b"] == 0
    p = compute_plan(s, list("abc"), False, BalancingConfig(strategy="custom", custom_targets={"b": 25}))
    assert {r["label"]: r["projected"] for r in p["classes"]} == {"a": 100, "b": 25, "c": 20}
    p = compute_plan(s, list("abc"), False, BalancingConfig(per_class_cap=5))
    assert {r["label"]: r["additional"] for r in p["classes"]}["b"] == 5


def test_multilabel_plan_accounts_for_cooccurrence():
    ml = [{"image_id": f"m{i}", "labels": ["normal"] if i < 180 else ["pneumonia"] if i < 260 else ["tb", "pneumonia"] if i < 290 else ["tb"]} for i in range(300)]
    p = compute_plan(ml, ["normal", "pneumonia", "tb"], True, BalancingConfig(max_expansion_factor=5))
    dist = projected_distribution(ml, p["assignments"])
    assert dist["tb"] >= 170 and dist["normal"] == 180          # rare label brought (nearly) to target
    assert dist["pneumonia"] > 180                               # co-occurrence overshoot is reported, not hidden
    assert max(a["n_variants"] for a in p["assignments"]) <= 4   # per-image expansion cap
