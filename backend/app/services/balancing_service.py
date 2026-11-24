"""Balancing planner (design §5): decides how many augmented variants each source image gets.

Pure functions, no I/O. Input is a list of {image_id, labels}; output is a plan that is
shown to the user *before* any job runs and recomputed server-side when a job is created.

Single-label: per-class need = max(0, min(target, original*max_factor, original+cap) - original),
spread as evenly as possible across that class's images.

Multilabel: one variant increments *every* label of its source, so a greedy loop repeatedly
serves the label furthest below its target, choosing the source that helps the most deficit
labels while penalising labels already at/over target. Exact equality is not promised.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from ..utils.common import AppError, stable_entropy

STRATEGIES = ("target_count", "balance_largest", "custom")


@dataclass
class BalancingConfig:
    strategy: str = "balance_largest"
    target_count: int | None = None
    custom_targets: dict[str, int] = field(default_factory=dict)
    max_expansion_factor: float = 10.0  # class may grow to at most factor x its original size
    per_class_cap: int | None = None  # max additional samples attributable to one class
    max_total_additional: int | None = None
    excluded_classes: list[str] = field(default_factory=list)
    seed: int = 42

    @classmethod
    def from_dict(cls, raw: dict | None) -> "BalancingConfig":
        raw = dict(raw or {})
        cfg = cls(**{k: raw[k] for k in cls.__dataclass_fields__ if k in raw and raw[k] is not None})
        if cfg.strategy not in STRATEGIES:
            raise AppError(f"strategy must be one of {STRATEGIES}", 400, "invalid_config")
        if cfg.strategy == "target_count" and (not cfg.target_count or cfg.target_count < 1):
            raise AppError("target_count must be a positive integer for the 'target_count' strategy", 400, "invalid_config")
        if cfg.strategy == "custom" and not cfg.custom_targets:
            raise AppError("custom_targets is required for the 'custom' strategy", 400, "invalid_config")
        if cfg.max_expansion_factor < 1:
            raise AppError("max_expansion_factor must be at least 1", 400, "invalid_config")
        return cfg

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def desired_targets(counts: dict[str, int], cfg: BalancingConfig) -> dict[str, int]:
    """Target total per class before caps. Classes are never reduced (no undersampling)."""
    largest = max(counts.values(), default=0)
    out = {}
    for label, n in counts.items():
        if cfg.strategy == "balance_largest":
            t = largest
        elif cfg.strategy == "target_count":
            t = cfg.target_count or n
        else:
            t = cfg.custom_targets.get(label, n)
        out[label] = max(int(t), n)
    return out


def _max_total(n: int, cfg: BalancingConfig) -> tuple[int, str | None]:
    """Largest allowed class total given the expansion/cap limits, and which limit binds."""
    by_factor = int(math.floor(n * cfg.max_expansion_factor))
    limit, why = by_factor, "max_expansion_factor"
    if cfg.per_class_cap is not None and n + cfg.per_class_cap < limit:
        limit, why = n + cfg.per_class_cap, "per_class_cap"
    return limit, why


def compute_plan(samples: list[dict], classes: list[str], multilabel: bool, cfg: BalancingConfig) -> dict:
    if not samples:
        raise AppError("There are no training samples to plan augmentation for", 400, "no_samples")
    counts = {c: 0 for c in classes}
    for s in samples:
        for lab in s["labels"]:
            counts[lab] = counts.get(lab, 0) + 1
    desired = desired_targets(counts, cfg)
    excluded = set(cfg.excluded_classes)
    unknown = (excluded | set(cfg.custom_targets)) - set(counts)
    if unknown:
        raise AppError(f"Unknown class(es): {sorted(unknown)}", 400, "unknown_class")
    rng = np.random.default_rng(stable_entropy("plan", cfg.seed))
    warnings: list[str] = []

    if multilabel:
        uses, projected, capped = _plan_multilabel(samples, counts, desired, excluded, cfg, rng, warnings)
    else:
        uses, projected, capped = _plan_single(samples, counts, desired, excluded, cfg, rng, warnings)

    total_additional = sum(uses.values())
    class_rows = []
    for c in sorted(counts):
        n = counts[c]
        class_rows.append({
            "label": c, "original": n, "target": desired[c], "projected": projected[c], "additional": projected[c] - n,  # label occurrences added (multilabel: includes co-occurring labels)
            "excluded": c in excluded, "capped_by": capped.get(c),
            "shortfall": max(0, desired[c] - projected[c]) if c not in excluded else 0,
        })
        if n == 0:
            warnings.append(f"Class '{c}' has no training samples, so nothing can be augmented for it.")
    for row in class_rows:
        if row["shortfall"] and row["capped_by"]:
            warnings.append(f"Class '{row['label']}' reaches {row['projected']} of target {row['target']} (limited by {row['capped_by'].replace('_', ' ')}).")
    if multilabel:
        for row in class_rows:
            if row["projected"] > 1.1 * max(row["target"], row["original"]) and row["additional"] > 0:
                warnings.append(f"Label '{row['label']}' is projected at {row['projected']} (target {row['target']}): it co-occurs with labels being oversampled.")
        warnings += _combination_warnings(samples, uses, counts, desired)
    if cfg.max_total_additional is not None and total_additional >= cfg.max_total_additional:
        warnings.append(f"Plan truncated at max_total_additional={cfg.max_total_additional}.")
    return {
        "annotation_type": "multilabel" if multilabel else "single",
        "config": cfg.to_dict(),
        "classes": class_rows,
        "assignments": [{"source_image_id": i, "n_variants": n} for i, n in sorted(uses.items()) if n > 0],
        "total_additional": total_additional,
        "total_original": len(samples),
        "projected_total": len(samples) + total_additional,
        "warnings": warnings,
    }


def _plan_single(samples, counts, desired, excluded, cfg, rng, warnings):
    by_class: dict[str, list[str]] = {}
    for s in samples:
        by_class.setdefault(s["labels"][0], []).append(s["image_id"])
    uses: dict[str, int] = {}
    projected, capped = dict(counts), {}
    budget = cfg.max_total_additional
    for c in sorted(counts):
        n = counts[c]
        if c in excluded or n == 0 or desired[c] <= n:
            continue
        limit, why = _max_total(n, cfg)
        goal = min(desired[c], limit)
        if goal < desired[c]:
            capped[c] = why
        need = max(0, goal - n)
        if budget is not None:
            need, budget = min(need, budget), budget - min(need, budget)
            if need == 0 and goal > n:
                capped[c] = "max_total_additional"
        ids = list(by_class[c])
        rng.shuffle(ids)
        base, extra = divmod(need, len(ids))
        for k, image_id in enumerate(ids):
            if (v := base + (1 if k < extra else 0)):
                uses[image_id] = v
        projected[c] = n + need
    return uses, projected, capped


def _plan_multilabel(samples, counts, desired, excluded, cfg, rng, warnings):
    eligible = [s for s in samples if not (set(s["labels"]) & excluded)]
    skipped = len(samples) - len(eligible)
    if skipped:
        warnings.append(f"{skipped} image(s) carry an excluded label and will not be augmented.")
    max_uses = max(0, int(math.floor(cfg.max_expansion_factor)) - 1)
    ceiling = {c: _max_total(n, cfg)[0] for c, n in counts.items()}
    by_label: dict[str, list[dict]] = {}
    for s in eligible:
        for lab in s["labels"]:
            by_label.setdefault(lab, []).append(s)
    current, uses, capped = dict(counts), Counter(), {}
    goal = {c: min(desired[c], ceiling[c]) for c in counts}
    for c in counts:
        if goal[c] < desired[c] and c not in excluded:
            capped[c] = _max_total(counts[c], cfg)[1]
    total, limit = 0, cfg.max_total_additional if cfg.max_total_additional is not None else 10**9
    open_labels = {c for c in counts if c not in excluded and goal[c] > counts[c] and by_label.get(c)}
    jitter = {s["image_id"]: float(rng.random()) for s in eligible}
    while open_labels and total < limit:
        lab = max(sorted(open_labels), key=lambda c: (goal[c] - current[c]) / max(goal[c], 1))
        cands = [s for s in by_label[lab] if uses[s["image_id"]] < max_uses and all(current[l] < ceiling[l] for l in s["labels"])]
        if not cands:
            open_labels.discard(lab)
            capped.setdefault(lab, "max_expansion_factor")
            continue

        def score(s):
            gain = sum((goal[l] - current[l]) / max(goal[l], 1) if current[l] < goal[l] else -1.0 for l in s["labels"])
            return (gain, -uses[s["image_id"]], jitter[s["image_id"]])

        pick = max(cands, key=score)
        uses[pick["image_id"]] += 1
        total += 1
        for l in pick["labels"]:
            current[l] += 1
        open_labels = {c for c in open_labels if current[c] < goal[c]}
    for c in counts:
        if c not in excluded and current[c] < desired[c] and c not in capped:
            capped[c] = "no_eligible_samples" if not by_label.get(c) else "max_expansion_factor"
    return dict(uses), current, capped


def _combination_warnings(samples, uses, counts, desired) -> list[str]:
    combo_orig, combo_new = Counter(), Counter()
    for s in samples:
        key = "+".join(sorted(s["labels"]))
        combo_orig[key] += 1
        combo_new[key] += uses.get(s["image_id"], 0)
    out = []
    total_new = sum(combo_new.values())
    for key, new in combo_new.items():
        labels = key.split("+")
        over = [l for l in labels if counts[l] >= desired[l]]
        if total_new and new > 2 * combo_orig[key] and over:
            out.append(f"Combination '{key}' grows from {combo_orig[key]} to {combo_orig[key] + new} although {', '.join(over)} already meet(s) the target (over-amplification risk).")
    return out


def projected_distribution(samples: list[dict], assignments: list[dict]) -> dict[str, int]:
    uses = {a["source_image_id"]: a["n_variants"] for a in assignments}
    dist: Counter = Counter()
    for s in samples:
        for lab in s["labels"]:
            dist[lab] += 1 + uses.get(s["image_id"], 0)
    return dict(dist)
