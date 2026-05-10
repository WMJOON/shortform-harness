"""orchestrator/tools.py — 오케스트레이터가 호출하는 도구 함수 모음."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline import loader, story_parser, scene_planner, scene_generator, subtitle_generator, pacing_engine, video_composer
from pipeline.loader import HARNESS_ROOT

RUNS_DIR = HARNESS_ROOT / "data" / "runs"
REGISTRY_PATH = HARNESS_ROOT / "registry" / "prompts" / "entries.jsonl"


def _assets_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id / "assets"


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
    return scene_generator.run(scene_grammar, h, _assets_dir(run_id), scene_ids)


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
    output_path = HARNESS_ROOT / "outputs" / f"{run_id}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return str(video_composer.run(timing_manifest, scene_grammar, _assets_dir(run_id), output_path, h))


# ── Run State Tools ────────────────────────────────────────────────────────

def new_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}_{uuid.uuid4().hex[:4]}"


def save_run_state(run_id: str, stage: str, data: Any) -> None:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "run_state.json"

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}

    state.update({"run_id": run_id, "current_stage": stage, "updated_at": datetime.now().isoformat(), stage: data})
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_run_state(run_id: str) -> dict:
    state_path = RUNS_DIR / run_id / "run_state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Run state not found: {run_id}")
    return json.loads(state_path.read_text(encoding="utf-8"))


# ── Prompt Registry Tools ──────────────────────────────────────────────────

def search_prompts(stage: str, tags: list[str] | None = None, top_k: int = 5) -> list[dict]:
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []

    results = [
        e for e in entries
        if e.get("stage") == stage and (not tags or any(t in e.get("tags", []) for t in tags))
    ]
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
    from consistency.checker import check_scene_grammar
    return check_scene_grammar(scene_grammar)


def check_pipeline_integrity(
    beat_structure: dict | None = None,
    scene_grammar: dict | None = None,
    timing_manifest: dict | None = None,
) -> list[dict]:
    from consistency.checker import check_beat_structure, check_scene_grammar, check_timing_manifest
    issues = []
    if beat_structure:
        issues.extend(check_beat_structure(beat_structure))
    if scene_grammar:
        issues.extend(check_scene_grammar(scene_grammar))
    if scene_grammar and timing_manifest:
        issues.extend(check_timing_manifest(timing_manifest, scene_grammar))
    return issues
