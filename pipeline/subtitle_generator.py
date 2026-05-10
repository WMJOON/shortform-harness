"""pipeline/subtitle_generator.py — Stage 4: scene_grammar → subtitle_tracks."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from pipeline.llm import call_llm, strip_code_fence, render_messages
from pipeline.loader import resolve_active_template
from pipeline.pacing_engine import build_subtitle_timing


def run(
    scene_grammar: dict,
    harness: dict,
    use_llm: bool = False,
) -> list[dict]:
    anchors = scene_grammar["consistency_anchors"]
    subtitle_config = anchors.get("subtitle", {})
    speed_wpm = anchors.get("voice", {}).get("speed_wpm", 180)

    if not use_llm:
        return [
            {"scene_id": sc["id"], "subtitle_timing": build_subtitle_timing(sc)}
            for sc in scene_grammar["scenes"]
        ]

    template = resolve_active_template(harness, "subtitle_generator")
    scenes = scene_grammar["scenes"]
    results: dict[int, list] = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_llm_subtitle, sc, subtitle_config, speed_wpm, template): sc["id"]
            for sc in scenes
        }
        for future in as_completed(futures):
            scene_id = futures[future]
            try:
                results[scene_id] = future.result()
            except Exception as exc:
                results[scene_id] = []

    return [{"scene_id": sc["id"], "subtitle_timing": results.get(sc["id"], [])} for sc in scenes]


def _llm_subtitle(
    scene: dict,
    subtitle_config: dict,
    speed_wpm: int,
    template: dict,
) -> list[dict]:
    system, user = render_messages(template, {
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
    })
    raw = strip_code_fence(call_llm(system, user, max_tokens=2048))
    result = json.loads(raw)
    return result if isinstance(result, list) else result.get("subtitle_timing", [])
