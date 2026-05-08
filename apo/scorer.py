"""
apo/scorer.py — rubric.yaml 기준 weighted score 계산

실제 구현에서는 사람 평가 + 자동 측정값을 모두 받아 계산한다.
"""

from __future__ import annotations

from pathlib import Path

import yaml

HARNESS_ROOT = Path(__file__).parent.parent
RUBRIC_PATH = HARNESS_ROOT / "feedback" / "rubric.yaml"


def score(measurements: dict) -> dict:
    """
    Args:
        measurements: {dimension: {criterion: value}} 형태
            예: {"hook": {"within_2_5s": True, "question_format": True, "target_address": False},
                 "human": {"overall_match": 8.0}}

    Returns:
        {"total": float, "dimensions": {dim: float}, "raw": measurements}
    """
    rubric = _load_rubric()
    dim_scores = {}

    for dim_name, dim_cfg in rubric["dimensions"].items():
        weight = dim_cfg.get("weight", 0.0)
        criteria = dim_cfg.get("criteria", {})
        dim_vals = measurements.get(dim_name, {})

        dim_score = _score_dimension(criteria, dim_vals)
        dim_scores[dim_name] = {"score": dim_score, "weight": weight, "weighted": dim_score * weight}

    # dim_score는 이미 0~10 범위 → weighted average만 계산
    total = sum(v["weighted"] for v in dim_scores.values())
    total_weight = sum(v["weight"] for v in dim_scores.values())
    normalized = total / total_weight if total_weight > 0 else 0.0

    return {
        "total": round(normalized, 2),
        "dimensions": {k: round(v["score"], 2) for k, v in dim_scores.items()},
        "raw": measurements,
    }


def _score_dimension(criteria: dict, values: dict) -> float:
    """dimension 내 criteria 평균 점수 (0~10)."""
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
            diff = abs(float(val) - target)
            scores.append(max(0.0, 10.0 - (diff / tol) * 10))

    return sum(scores) / len(scores) if scores else 0.0


def _load_rubric() -> dict:
    with open(RUBRIC_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def needs_apo(score_result: dict, harness: dict) -> bool:
    """APO 루프 진입 여부 판단."""
    apo_cfg = harness.get("apo", {})
    if not apo_cfg.get("enabled", False):
        return False
    trigger = apo_cfg.get("min_score_delta", 0.15)
    max_score = harness.get("apo", {}).get("target_score", 9.0)
    return score_result["total"] < (max_score - trigger * 10)
