"""
apo/optimizer.py — meta-prompt으로 후보 템플릿 생성

낮은 dimension에 집중해 현재 템플릿의 개선 버전을 생성한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

HARNESS_ROOT = Path(__file__).parent.parent
CANDIDATES_DIR = HARNESS_ROOT / "apo" / "candidates"
HISTORY_PATH = HARNESS_ROOT / "apo" / "history" / "runs.jsonl"


def optimize(
    stage: str,
    current_template: dict,
    score_result: dict,
    run_id: str,
) -> dict:
    """
    낮은 점수 dimension을 분석해 개선된 템플릿 후보를 생성한다.

    Returns:
        새 템플릿 dict (candidates/ 에도 저장)
    """
    weak_dims = _find_weak_dimensions(score_result)
    meta_prompt = _build_meta_prompt(stage, current_template, score_result, weak_dims)
    candidate_template = _call_llm_for_template(meta_prompt)

    candidate_path = _save_candidate(stage, candidate_template, run_id)
    _record_history(stage, run_id, score_result, str(candidate_path))

    return candidate_template


def _find_weak_dimensions(score_result: dict, threshold: float = 6.0) -> list[str]:
    return [
        dim for dim, score in score_result.get("dimensions", {}).items()
        if score < threshold
    ]


def _build_meta_prompt(
    stage: str,
    current_template: dict,
    score_result: dict,
    weak_dims: list[str],
) -> str:
    weak_summary = ", ".join(f"{d}({score_result['dimensions'].get(d, 0):.1f}/10)" for d in weak_dims)
    return f"""You are a prompt engineer optimizing a shortform video generation template.

Current template stage: {stage}
Current score: {score_result['total']}/10
Weak dimensions: {weak_summary}

Current system prompt:
{current_template.get('system', '')}

Current user prompt:
{current_template.get('user', '')}

Generate an improved template that specifically addresses the weak dimensions.
Focus on:
{chr(10).join(f'- {d}: strengthen constraints/instructions' for d in weak_dims)}

Return the improved template in the same YAML structure.
Only modify the system and user fields. Keep id, stage, version (increment minor), input, output, eval_cases unchanged.
"""


def _call_llm_for_template(meta_prompt: str) -> dict:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": meta_prompt}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
        return yaml.safe_load(text)
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")


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
