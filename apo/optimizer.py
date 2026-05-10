"""apo/optimizer.py — meta-prompt으로 후보 템플릿 생성."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from pipeline.llm import call_llm, strip_code_fence
from pipeline.loader import HARNESS_ROOT

CANDIDATES_DIR = HARNESS_ROOT / "apo" / "candidates"
HISTORY_PATH = HARNESS_ROOT / "apo" / "history" / "runs.jsonl"


def optimize(
    stage: str,
    current_template: dict,
    score_result: dict,
    run_id: str,
) -> dict:
    weak_dims = _find_weak_dimensions(score_result)
    meta_prompt = _build_meta_prompt(stage, current_template, score_result, weak_dims)
    candidate_template = yaml.safe_load(strip_code_fence(call_llm("", meta_prompt, max_tokens=4096)))

    candidate_path = _save_candidate(stage, candidate_template, run_id)
    _record_history(stage, run_id, score_result, str(candidate_path))
    return candidate_template


def _find_weak_dimensions(score_result: dict, threshold: float = 6.0) -> list[str]:
    return [
        dim for dim, s in score_result.get("dimensions", {}).items()
        if s < threshold
    ]


def _build_meta_prompt(
    stage: str,
    current_template: dict,
    score_result: dict,
    weak_dims: list[str],
) -> str:
    weak_summary = ", ".join(
        f"{d}({score_result['dimensions'].get(d, 0):.1f}/10)" for d in weak_dims
    )
    focus = "\n".join(f"- {d}: strengthen constraints/instructions" for d in weak_dims)
    return f"""You are a prompt engineer optimizing a shortform video generation template.

Stage: {stage}
Current score: {score_result['total']}/10
Weak dimensions: {weak_summary}

Current system prompt:
{current_template.get('system', '')}

Current user prompt:
{current_template.get('user', '')}

Generate an improved template addressing the weak dimensions:
{focus}

Return the improved template in the same YAML structure.
Only modify the system and user fields.
"""


def _save_candidate(stage: str, template: dict, run_id: str) -> Path:
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CANDIDATES_DIR / f"{stage}_{run_id}_{ts}.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(template, f, allow_unicode=True, default_flow_style=False)
    return path


def _record_history(stage: str, run_id: str, score_result: dict, candidate_path: str) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "stage": stage,
        "run_id": run_id,
        "score": score_result["total"],
        "candidate_path": candidate_path,
        "created_at": datetime.now().isoformat(),
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
