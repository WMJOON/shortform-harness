"""
pipeline/scene_planner.py — Stage 2: beat_structure → scene_grammar

활성 템플릿으로 Claude API를 호출해 SceneGrammar JSON을 생성한다.
"""

from __future__ import annotations

import json

from pipeline.loader import resolve_active_template, resolve_active_properties, load_style_profile


def run(
    beat_structure: dict,
    harness: dict,
    style_profile: dict | None = None,
) -> dict:
    """
    Returns:
        scene_grammar dict matching schemas/scene_grammar.schema.json
    """
    template = resolve_active_template(harness, "scene_planner")
    props = resolve_active_properties(harness)
    profile = style_profile or load_style_profile()

    # pacing_rules from harness
    pacing_rules = (
        harness.get("stages", {}).get("pacing_engine", {}).get("pacing_rules", {})
    )

    messages = _render_messages(template, beat_structure, profile, pacing_rules, props)
    response = _call_llm(messages)
    scene_grammar = _parse_json(response)
    _validate(scene_grammar, beat_structure)
    return scene_grammar


def _render_messages(
    template: dict,
    beat_structure: dict,
    style_profile: dict,
    pacing_rules: dict,
    props: dict,
) -> list[dict]:
    anchors = style_profile.get("consistency_anchors", {})
    narrative = style_profile.get("narrative", {})

    vars = {
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

    def render(text: str) -> str:
        for k, v in vars.items():
            text = text.replace(f"{{{{ {k} }}}}", str(v))
        return text

    return [
        {"role": "system", "content": render(template["system"])},
        {"role": "user",   "content": render(template["user"])},
    ]


def _call_llm(messages: list[dict]) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
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


def _validate(scene_grammar: dict, beat_structure: dict) -> None:
    scenes = scene_grammar.get("scenes", [])
    if not scenes:
        raise ValueError("scenes is empty")
    if scenes[0].get("scene_type") != "hook":
        raise ValueError(f"scenes[0].scene_type must be 'hook', got '{scenes[0].get('scene_type')}'")
    if scenes[-1].get("scene_type") != "cta":
        raise ValueError(f"scenes[-1].scene_type must be 'cta', got '{scenes[-1].get('scene_type')}'")

    total = beat_structure.get("total_duration_sec", 0)
    duration_sum = sum(s.get("duration", 0) for s in scenes)
    if abs(duration_sum - total) > 0.5:
        raise ValueError(
            f"scene duration sum {duration_sum:.2f}s deviates from total {total}s by >{0.5}s"
        )
