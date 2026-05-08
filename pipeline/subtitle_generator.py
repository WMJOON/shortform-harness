"""
pipeline/subtitle_generator.py — Stage 4: scene_grammar → subtitle_tracks

모든 씬의 voiceover에 대해 subtitle_timing 배열을 생성한다.
LLM 호출(세밀한 타이밍) 또는 rule-based fallback(균등 분할) 중 선택.
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.loader import resolve_active_template
from pipeline.pacing_engine import _build_subtitle_timing


def run(
    scene_grammar: dict,
    harness: dict,
    use_llm: bool = False,
) -> list[dict]:
    """
    Returns:
        subtitle_tracks: [{scene_id, subtitle_timing: [...]}, ...]
    """
    template = resolve_active_template(harness, "subtitle_generator") if use_llm else None
    anchors = scene_grammar["consistency_anchors"]
    subtitle_config = anchors.get("subtitle", {})
    speed_wpm = anchors.get("voice", {}).get("speed_wpm", 180)

    tracks = []
    for scene in scene_grammar["scenes"]:
        if use_llm and template:
            timing = _llm_subtitle(scene, subtitle_config, speed_wpm, template)
        else:
            timing = _rule_subtitle(scene)

        tracks.append({"scene_id": scene["id"], "subtitle_timing": timing})

    return tracks


def _rule_subtitle(scene: dict) -> list[dict]:
    """rule-based fallback: pacing_engine의 균등 분할 사용."""
    return _build_subtitle_timing(scene, start_offset_ms=0)


def _llm_subtitle(
    scene: dict,
    subtitle_config: dict,
    speed_wpm: int,
    template: dict,
) -> list[dict]:
    """LLM 기반 정밀 자막 타이밍 생성."""
    vars = {
        "scene.id": scene["id"],
        "scene.duration": scene["duration"],
        "scene.voiceover": scene.get("voiceover", ""),
        "scene.subtitle_density": scene.get("subtitle_density", "medium"),
        "scene.caption_style": scene.get("caption_style", "normal"),
        "subtitle_config.font": subtitle_config.get("font", ""),
        "subtitle_config.color": subtitle_config.get("color", "#FFFFFF"),
        "subtitle_config.position": subtitle_config.get("position", "bottom"),
        "subtitle_config.emphasis_color": subtitle_config.get("emphasis_color", "#FFE566"),
        "tts_words_per_min": speed_wpm,
    }

    def render(text: str) -> str:
        for k, v in vars.items():
            text = text.replace(f"{{{{ {k} }}}}", str(v))
        return text

    system_msg = render(template["system"])
    user_msg = render(template["user"])

    raw = _call_llm(system_msg, user_msg)
    return _parse_json(raw)


def _call_llm(system: str, user: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")


def _parse_json(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    result = json.loads(text)
    return result if isinstance(result, list) else result.get("subtitle_timing", [])
