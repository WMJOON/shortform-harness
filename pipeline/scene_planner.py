"""pipeline/scene_planner.py — Stage 2: beat_structure → scene_grammar."""

from __future__ import annotations

import json

from pipeline.llm import call_llm, strip_code_fence, render_messages, _resolve_backend
from pipeline.loader import resolve_active_template, resolve_active_properties, load_style_profile, resolve_pacing_rules
from pipeline.constants import SceneType


def run(
    beat_structure: dict,
    harness: dict,
    style_profile: dict | None = None,
) -> dict:
    template = resolve_active_template(harness, "scene_planner")
    props = resolve_active_properties(harness)
    profile = style_profile or load_style_profile()
    pacing_rules = resolve_pacing_rules(harness)

    gen = harness.get("generation", {})
    llm_backend = gen.get("llm_backend", "auto")
    effective_backend = _resolve_backend() if (not llm_backend or llm_backend == "auto") else llm_backend
    llm_model   = gen.get("llm_model", {}).get(effective_backend)
    system, user = render_messages(template, _build_vars(beat_structure, profile, pacing_rules, props))
    scene_grammar = json.loads(strip_code_fence(call_llm(system, user, max_tokens=4096, backend=llm_backend, model=llm_model)))
    _validate(scene_grammar, beat_structure)
    return scene_grammar


def _build_vars(
    beat_structure: dict,
    style_profile: dict,
    pacing_rules: dict,
    props: dict,
) -> dict:
    anchors = style_profile.get("consistency_anchors", {})
    narrative = style_profile.get("narrative", {})
    return {
        "beat_structure": json.dumps(beat_structure, ensure_ascii=False, indent=2),
        "pacing_rules.hook_max_duration": pacing_rules.get("hook_max_duration", 2.5),
        "pacing_rules.avg_scene_length": pacing_rules.get("avg_scene_length", 1.7),
        "pacing_rules.zoom_probability": pacing_rules.get("zoom_probability", 0.4),
        "style_profile.narrative.target_persona": narrative.get("target_persona", ""),
        "style_profile.hook.type": style_profile.get("hook", {}).get("type", "question"),
        "style_profile.narrative.ppl_bridge_phrase": narrative.get("ppl_bridge_phrase", ""),
        "style_profile.consistency_anchors.character.description":
            anchors.get("character", {}).get("description", ""),
        "style_profile.consistency_anchors.background.description":
            anchors.get("background", {}).get("description", ""),
        "active_properties": json.dumps(props["values"], ensure_ascii=False, indent=2),
        "beat_structure.total_duration_sec": beat_structure.get("total_duration_sec", 30),
    }


def _validate(scene_grammar: dict, beat_structure: dict) -> None:
    scenes = scene_grammar.get("scenes", [])
    if not scenes:
        raise ValueError("scenes is empty")
    if scenes[0].get("scene_type") != SceneType.HOOK:
        raise ValueError(f"scenes[0].scene_type must be 'hook', got '{scenes[0].get('scene_type')}'")
    if scenes[-1].get("scene_type") != SceneType.CTA:
        raise ValueError(f"scenes[-1].scene_type must be 'cta', got '{scenes[-1].get('scene_type')}'")

    total = beat_structure.get("total_duration_sec", 0)
    duration_sum = sum(s.get("duration", 0) for s in scenes)
    if abs(duration_sum - total) > 0.5:
        raise ValueError(
            f"scene duration sum {duration_sum:.2f}s deviates from total {total}s by >0.5s"
        )
