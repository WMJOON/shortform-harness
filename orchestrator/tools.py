"""
orchestrator/tools.py — 오케스트레이터가 호출하는 도구 함수 모음

각 함수는 tool_use 형태로 오케스트레이터에 노출된다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline import (
    loader,
    story_parser,
    scene_planner,
    scene_generator,
    subtitle_generator,
    pacing_engine,
    video_composer,
)

HARNESS_ROOT = Path(__file__).parent.parent
RUNS_DIR = HARNESS_ROOT / "data" / "runs"
REGISTRY_PATH = HARNESS_ROOT / "registry" / "prompts" / "entries.jsonl"


# ── Pipeline Stage Tools ───────────────────────────────────────────────────

def run_story_parser(prompt: str, duration: float, harness: dict | None = None) -> dict:
    h = harness or loader.load_harness()
    return story_parser.run(prompt, duration, h)


def run_scene_planner(beat_structure: dict, harness: dict | None = None) -> dict:
    h = harness or loader.load_harness()
    return scene_planner.run(beat_structure, h)


def run_scene_generator(
    scene_grammar: dict,
    run_id: str,
    scene_ids: list[int] | None = None,
    harness: dict | None = None,
) -> dict:
    h = harness or loader.load_harness()
    assets_dir = RUNS_DIR / run_id / "assets"
    return scene_generator.run(scene_grammar, h, assets_dir, scene_ids)


def run_subtitle_generator(
    scene_grammar: dict,
    harness: dict | None = None,
    use_llm: bool = False,
) -> list[dict]:
    h = harness or loader.load_harness()
    return subtitle_generator.run(scene_grammar, h, use_llm)


def run_pacing_engine(scene_grammar: dict, harness: dict | None = None) -> dict:
    h = harness or loader.load_harness()
    pacing_rules = loader.resolve_pacing_rules(h)
    return pacing_engine.run(scene_grammar, pacing_rules)


def run_video_composer(
    timing_manifest: dict,
    scene_grammar: dict,
    run_id: str,
    harness: dict | None = None,
) -> str:
    h = harness or loader.load_harness()
    assets_dir = RUNS_DIR / run_id / "assets"
    output_path = HARNESS_ROOT / "outputs" / f"{run_id}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = video_composer.run(timing_manifest, scene_grammar, assets_dir, output_path, h)
    return str(result)


# ── Run State Tools ────────────────────────────────────────────────────────

def new_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}_{uuid.uuid4().hex[:4]}"


def save_run_state(run_id: str, stage: str, data: Any) -> None:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "run_state.json"

    state: dict = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    state["run_id"] = run_id
    state["current_stage"] = stage
    state["updated_at"] = datetime.now().isoformat()
    state[stage] = data

    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_run_state(run_id: str) -> dict:
    state_path = RUNS_DIR / run_id / "run_state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Run state not found: {run_id}")
    return json.loads(state_path.read_text(encoding="utf-8"))


# ── Prompt Registry Tools ──────────────────────────────────────────────────

def search_prompts(stage: str, tags: list[str] | None = None, top_k: int = 5) -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []

    results = []
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line.strip())
            if entry.get("stage") != stage:
                continue
            if tags and not any(t in entry.get("tags", []) for t in tags):
                continue
            results.append(entry)

    results.sort(key=lambda e: e.get("score", 0), reverse=True)
    return results[:top_k]


def save_prompt(
    stage: str,
    version: str,
    params: dict,
    score: float,
    tags: list[str],
    run_id: str | None = None,
) -> str:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry_id = f"{stage[:2]}_{uuid.uuid4().hex[:8]}"
    entry = {
        "id": entry_id,
        "stage": stage,
        "template_version": version,
        "params": params,
        "score": score,
        "tags": tags,
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
    }
    with open(REGISTRY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry_id


# ── Validation Tools ───────────────────────────────────────────────────────

def check_consistency(scene_grammar: dict) -> list[dict]:
    """consistency/properties.yaml 기준 property별 일관성 검사 (stub)."""
    # TODO: CLIP 임베딩, RMS 분석 등 실제 구현
    issues = []
    anchors = scene_grammar.get("consistency_anchors", {})
    for scene in scene_grammar.get("scenes", []):
        if not scene.get("visual_prompt", "").strip():
            issues.append({
                "scene_id": scene["id"],
                "property": "character.visual",
                "issue": "visual_prompt is empty",
                "severity": "error",
            })
    return issues


def check_pipeline_integrity(
    beat_structure: dict | None = None,
    scene_grammar: dict | None = None,
    timing_manifest: dict | None = None,
) -> list[dict]:
    """consistency/rules/pipeline_integrity.yaml 규칙 검사."""
    issues = []

    if beat_structure:
        beats = beat_structure.get("beats", [])
        if beats and beats[0].get("function") != "hook":
            issues.append({"rule": "PI002", "message": "First beat is not hook"})

        ratio_sum = sum(b.get("duration_ratio", 0) for b in beats)
        if abs(ratio_sum - 1.0) > 0.01:
            issues.append({"rule": "PI001", "message": f"duration_ratio sum={ratio_sum:.4f} ≠ 1.0"})

    if scene_grammar:
        scenes = scene_grammar.get("scenes", [])
        if scenes and scenes[0].get("scene_type") != "hook":
            issues.append({"rule": "PI002", "message": "scenes[0] is not hook"})

        ppl = scene_grammar.get("narrative", {}).get("ppl_present", False)
        has_product = any(s.get("scene_type") == "product_focus" for s in scenes)
        if ppl and not has_product:
            issues.append({"rule": "PI003", "message": "ppl_present but no product_focus scene"})

    if scene_grammar and timing_manifest:
        grammar_count = len(scene_grammar.get("scenes", []))
        timing_count = len(timing_manifest.get("scenes", []))
        if grammar_count != timing_count:
            issues.append({
                "rule": "PI004",
                "message": f"scene count mismatch: grammar={grammar_count}, timing={timing_count}",
            })

    return issues
