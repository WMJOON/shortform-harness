"""
pipeline/story_parser.py — Stage 1: user prompt → beat_structure

활성 템플릿을 로드해 Claude API를 호출하고 BeatStructure JSON을 반환한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.loader import resolve_active_template, resolve_active_properties, load_style_profile


def run(
    user_prompt: str,
    total_duration_sec: float,
    harness: dict,
    style_profile: dict | None = None,
) -> dict:
    """
    Returns:
        beat_structure dict matching schemas/beat_structure.schema.json
    """
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

    messages = _render_messages(template, {
        "user_prompt": user_prompt,
        "target_persona": target_persona,
        "total_duration_sec": total_duration_sec,
        "emotional_arc_pattern": emotional_arc,
    })

    response = _call_llm(messages, template)
    beat_structure = _parse_json(response)
    _validate(beat_structure)
    return beat_structure


def _render_messages(template: dict, vars: dict) -> list[dict]:
    def render(text: str) -> str:
        for k, v in vars.items():
            text = text.replace(f"{{{{ {k} }}}}", str(v))
        return text

    return [
        {"role": "system", "content": render(template["system"])},
        {"role": "user",   "content": render(template["user"])},
    ]


def _call_llm(messages: list[dict], template: dict) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=messages[0]["content"],
            messages=[{"role": "user", "content": messages[1]["content"]}],
        )
        return resp.content[0].text
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    return json.loads(text)


def _validate(beat_structure: dict) -> None:
    beats = beat_structure.get("beats", [])
    if not beats:
        raise ValueError("beats is empty")
    if beats[0].get("function") != "hook":
        raise ValueError(f"beats[0].function must be 'hook', got '{beats[0].get('function')}'")
    if beats[-1].get("function") != "cta":
        raise ValueError(f"beats[-1].function must be 'cta', got '{beats[-1].get('function')}'")

    total_ratio = sum(b.get("duration_ratio", 0) for b in beats)
    if abs(total_ratio - 1.0) > 0.01:
        raise ValueError(f"duration_ratio sum must be 1.0, got {total_ratio:.4f}")
