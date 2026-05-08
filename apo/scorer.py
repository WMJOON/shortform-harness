"""apo/scorer.py — rubric.yaml 기준 weighted score 계산."""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

from pipeline.loader import HARNESS_ROOT

RUBRIC_PATH = HARNESS_ROOT / "feedback" / "rubric.yaml"


def score(measurements: dict) -> dict:
    rubric = _load_rubric()
    dim_scores = {
        name: {
            "score": _score_dimension(cfg.get("criteria", {}), measurements.get(name, {})),
            "weight": cfg.get("weight", 0.0),
        }
        for name, cfg in rubric["dimensions"].items()
    }
    for v in dim_scores.values():
        v["weighted"] = v["score"] * v["weight"]

    total_weight = sum(v["weight"] for v in dim_scores.values())
    normalized = sum(v["weighted"] for v in dim_scores.values()) / total_weight if total_weight else 0.0

    return {
        "total": round(normalized, 2),
        "dimensions": {k: round(v["score"], 2) for k, v in dim_scores.items()},
        "raw": measurements,
    }


def _score_dimension(criteria: dict, values: dict) -> float:
    scores = []
    for crit_name, crit_cfg in criteria.items():
        val = values.get(crit_name)
        if val is None:
            continue
        crit_type = crit_cfg.get("type")
        if crit_type == "binary":
            scores.append(10.0 if val else 0.0)
        elif crit_type == "scale":
            r = crit_cfg.get("range", [0, 10])
            scores.append(float(val) / r[1] * 10)
        elif crit_type == "range":
            target = crit_cfg.get("target", 0)
            tol = crit_cfg.get("tolerance", 1)
            scores.append(max(0.0, 10.0 - (abs(float(val) - target) / tol) * 10))
    return sum(scores) / len(scores) if scores else 0.0


@functools.lru_cache(maxsize=1)
def _load_rubric() -> dict:
    with open(RUBRIC_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def needs_apo(score_result: dict, harness: dict) -> bool:
    apo_cfg = harness.get("apo", {})
    if not apo_cfg.get("enabled", False):
        return False
    target = apo_cfg.get("target_score", 9.0)
    delta = apo_cfg.get("min_score_delta", 0.15)
    return score_result["total"] < (target - delta * 10)
