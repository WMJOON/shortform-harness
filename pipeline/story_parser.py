"""pipeline/story_parser.py — Stage 1: user prompt → beat_structure."""

from __future__ import annotations

import json

from consistency.checker import check_beat_structure
from pipeline.llm import call_llm, strip_code_fence, render_messages, _resolve_backend
from pipeline.loader import resolve_active_template, resolve_active_properties, load_style_profile


def run(
    user_prompt: str,
    total_duration_sec: float,
    harness: dict,
    style_profile: dict | None = None,
) -> dict:
    template = resolve_active_template(harness, "story_parser")
    props = resolve_active_properties(harness)
    profile = style_profile or load_style_profile()

    target_persona = (
        profile.get("narrative", {}).get("target_persona")
        or props["values"].get("narrative.target_persona", "")
    )
    emotional_arc = (
        profile.get("narrative", {}).get("emotional_arc")
        or "curiosity→empathy→solution→desire→action"
    )

    system, user = render_messages(template, {
        "user_prompt": user_prompt,
        "target_persona": target_persona,
        "total_duration_sec": total_duration_sec,
        "emotional_arc_pattern": emotional_arc,
    })

    gen = harness.get("generation", {})
    llm_backend = gen.get("llm_backend", "auto")
    effective_backend = _resolve_backend() if (not llm_backend or llm_backend == "auto") else llm_backend
    llm_model   = gen.get("llm_model", {}).get(effective_backend)
    beat_structure = json.loads(strip_code_fence(call_llm(system, user, max_tokens=2048, backend=llm_backend, model=llm_model)))

    issues = check_beat_structure(beat_structure)
    errors = [i for i in issues if i["severity"] == "error"]
    if errors:
        raise ValueError("; ".join(i["message"] for i in errors))

    return beat_structure
