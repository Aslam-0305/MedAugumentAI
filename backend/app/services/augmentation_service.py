"""Augmentation planning and job creation (design §5, §7, §9 steps 6-8)."""
from __future__ import annotations

import platform
import random
import threading

import numpy as np
import scipy

from .. import APP_VERSION
from ..context import AppContext
from ..imaging.adapters import get_adapter
from ..imaging.pipeline import parse_pipeline_config
from ..imaging.transforms.registry import REGISTRY
from ..utils.common import AppError, new_id, to_jsonable, utcnow
from . import balancing_service as bal
from .analysis_service import training_samples
from .dataset_service import get_dataset


def transform_catalog(modality: str) -> dict:
    adapter = get_adapter(modality)
    items = []
    for name in adapter.allowed:
        info = REGISTRY[name]
        params, _ = adapter.resolve_params(name, None)
        items.append({
            "name": name, "label": info.label, "family": info.family, "kind": info.kind, "description": info.description,
            "defaults": params, "probability": info.probability, "limits": {k: list(v) for k, v in adapter.limits.get(name, {}).items()},
            "param_help": info.param_help, "caution": info.caution, "default_enabled": name in adapter.default_enabled,
            "requires_opt_in": name == "flip",
        })
    blocked = [{"name": n, "label": REGISTRY[n].label, "reason": adapter.blocked_reason.get(n, "not appropriate for this modality")}
               for n in REGISTRY if n not in adapter.allowed]
    return {"modality": modality, "label": adapter.label, "transforms": items, "blocked": blocked, "policy_notes": list(adapter.policy_notes)}


def build_plan(ctx: AppContext, dataset_id: str, balancing: dict | None, augmentation: dict | None) -> dict:
    ds = get_dataset(ctx, dataset_id)
    if ds["status"] == "failed":
        raise AppError("This dataset has no valid images to augment", 409, "dataset_failed")
    samples, splits_defined = training_samples(ctx, dataset_id)
    raw = dict(balancing or {})
    raw.setdefault("max_total_additional", ctx.settings.max_job_additional)
    cfg = bal.BalancingConfig.from_dict(raw)
    cfg.max_total_additional = min(cfg.max_total_additional or ctx.settings.max_job_additional, ctx.settings.max_job_additional)
    plan = bal.compute_plan(samples, ds["classes"], ds["annotation_type"] == "multilabel", cfg)
    pcfg, warns = parse_pipeline_config(ds["modality"], augmentation)
    warnings = list(plan["warnings"]) + warns
    if not splits_defined:
        warnings.insert(0, "No patient-level splits exist, so ALL images are treated as training data. Create splits first if you need validation/test data free of leakage.")
    size = {s["image_id"]: s.get("size_bytes", 0) for s in samples}
    est = sum(size.get(a["source_image_id"], 0) * a["n_variants"] for a in plan["assignments"])
    plan.update({
        "dataset_id": dataset_id, "modality": ds["modality"], "splits_defined": splits_defined, "warnings": warnings,
        "augmentation": pcfg.to_dict(), "estimated_storage_mb": round(est / 2**20, 1),
        "projected_distribution": bal.projected_distribution(samples, plan["assignments"]),
    })
    return plan


def _software() -> dict:
    from ..imaging.loaders.nifti_loader import _nib
    nib = _nib()
    return {"app": APP_VERSION, "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "nibabel": getattr(nib, "__version__", None)}


def create_job(ctx: AppContext, dataset_id: str, balancing: dict | None, augmentation: dict | None,
               seed: int | None = None, name: str | None = None) -> dict:
    from ..workers.augmentation_worker import run_augmentation_job
    ds = get_dataset(ctx, dataset_id)
    balancing = dict(balancing or {})
    seed = int(seed if seed is not None else random.SystemRandom().randrange(1, 2**31 - 1))
    balancing["seed"] = seed
    plan = build_plan(ctx, dataset_id, balancing, augmentation)  # authoritative server-side recomputation
    if plan["total_additional"] == 0:
        raise AppError("The plan generates no additional samples. Adjust targets or caps.", 400, "nothing_to_do")
    job_id = new_id("job")
    total = plan["total_additional"]
    job = {
        "job_id": job_id, "dataset_id": dataset_id, "name": (name or f"{ds['name']} augmentation").strip(), "modality": ds["modality"],
        "status": "queued", "created_at": utcnow(), "started_at": None, "completed_at": None, "error": None,
        "seed": seed, "config": {"balancing": plan["config"], "augmentation": plan["augmentation"], "materialization": "materialized"},
        "plan": {k: plan[k] for k in ("annotation_type", "classes", "assignments", "total_additional", "total_original", "warnings", "splits_defined", "projected_distribution")},
        "progress": {"total": total, "done": 0, "accepted": 0, "warnings": 0, "rejected": 0, "failed": 0, "percent": 0.0},
        "logs": [{"t": utcnow(), "msg": f"Job queued: {total} samples planned"}], "cancel_requested": False,
        "software": _software(), "summary": None,
    }
    ctx.store.insert_one("augmentation_jobs", to_jsonable(job))
    ctx.cancel_events[job_id] = threading.Event()
    ctx.executor.submit(run_augmentation_job, ctx, job_id)
    return {k: v for k, v in job.items() if k != "plan"} | {"plan_summary": {"total_additional": total}}


def preview_augmentation(ctx: AppContext, dataset_id: str, image_id: str, augmentation: dict | None, seed: int = 0,
                         channel: int = 0, slice_index: int | None = None) -> bytes:
    """Render one throw-away augmented example (never persisted) so users can judge parameters."""
    from ..imaging.loaders import load_image_set
    from ..imaging.pipeline import AugmentationPipeline
    from ..utils.common import stable_entropy
    from .preview_service import render_array
    ds = get_dataset(ctx, dataset_id)
    im = ctx.store.find_one("images", {"image_id": image_id, "dataset_id": dataset_id, "status": "valid"})
    if not im:
        raise AppError(f"Image '{image_id}' not found in this dataset", 404, "not_found")
    pcfg, _ = parse_pipeline_config(ds["modality"], augmentation)
    src = load_image_set([ctx.storage.path(k) for k in im["file_paths"]], ds["modality"])
    out, _ = AugmentationPipeline(pcfg).run(src, np.random.default_rng(stable_entropy("preview", seed, image_id)))
    return render_array(out, channel=channel, slice_index=slice_index, modality=ds["modality"])
