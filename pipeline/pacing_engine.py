"""pipeline/pacing_engine.py — rule-based Pacing Engine (LLM 없음).

scene_grammar + pacing_rules → timing_manifest.json
모든 계산은 결정론적(deterministic)이다.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from pipeline.constants import SceneType, SubtitleDensity


def run(scene_grammar: dict, pacing_rules: dict, seed: int = 42) -> dict:
    rng = random.Random(seed)
    scenes_in = scene_grammar["scenes"]
    total_dur = scene_grammar["narrative"]["total_duration_sec"]

    zoom_prob = pacing_rules.get("zoom_probability", 0.4)
    bgm_duck_ratio = pacing_rules.get("bgm_duck_ratio", 0.3)

    scenes_out: list[dict[str, Any]] = []
    cursor = 0.0

    for sc in scenes_in:
        duration = sc["duration"]
        start = round(cursor, 3)
        end = round(cursor + duration, 3)
        zoom = sc.get("zoom", rng.random() < zoom_prob)

        scenes_out.append({
            "id": sc["id"],
            "start_sec": start,
            "end_sec": end,
            "zoom": zoom,
            "transition_out": sc.get("transition_out", "cut"),
            "bgm": {"cue": sc.get("bgm_cue", "continue")},
            "subtitle_timing": build_subtitle_timing(sc),
        })

        cursor = end

    return {
        "total_duration_sec": total_dur,
        "bgm_track": pacing_rules.get("bgm_track", ""),
        "bgm_duck_points": _build_duck_points(scenes_out, scenes_in, bgm_duck_ratio),
        "scenes": scenes_out,
    }


def build_subtitle_timing(scene: dict, start_offset_ms: int = 0) -> list[dict]:
    """voiceover 텍스트를 duration에 맞게 균등 분할."""
    voiceover = scene.get("voiceover", "").strip()
    duration_ms = int(scene["duration"] * 1000)
    density = scene.get("subtitle_density", SubtitleDensity.MEDIUM)

    if density == SubtitleDensity.NONE or not voiceover:
        return []

    words = voiceover.split()
    if not words:
        return []

    words_per_seg = {SubtitleDensity.LOW: 6, SubtitleDensity.MEDIUM: 4, SubtitleDensity.HIGH: 2}.get(density, 4)
    segments = [words[i: i + words_per_seg] for i in range(0, len(words), words_per_seg)]
    ms_per_seg = duration_ms // max(len(segments), 1)

    result = []
    for i, seg_words in enumerate(segments):
        start_ms = start_offset_ms + i * ms_per_seg
        end_ms = start_offset_ms + (i + 1) * ms_per_seg
        text = " ".join(seg_words)
        emphasis = any(c.isdigit() or c in "!?" for c in text)
        result.append({
            "text": text,
            "start_ms": start_ms,
            "end_ms": min(end_ms, start_offset_ms + duration_ms),
            "emphasis": emphasis,
        })

    return result


def _build_duck_points(
    scenes_out: list[dict],
    scenes_in: list[dict],
    duck_ratio: float,
) -> list[dict]:
    return [
        {"start_sec": sc_out["start_sec"], "end_sec": sc_out["end_sec"], "ratio": duck_ratio}
        for sc_out, sc_in in zip(scenes_out, scenes_in)
        if sc_in.get("scene_type") == SceneType.PRODUCT_FOCUS
    ]


def validate_timing(timing_manifest: dict, scene_grammar: dict) -> list[str]:
    errors = []
    expected_count = len(scene_grammar["scenes"])
    actual_count = len(timing_manifest["scenes"])
    if expected_count != actual_count:
        errors.append(f"PI004: scene count mismatch — grammar={expected_count}, timing={actual_count}")

    total = timing_manifest["total_duration_sec"]
    actual_end = timing_manifest["scenes"][-1]["end_sec"] if timing_manifest["scenes"] else 0.0
    if abs(actual_end - total) > 0.5:
        errors.append(f"Duration mismatch: total={total}, actual_end={actual_end:.3f}")

    return errors


if __name__ == "__main__":
    import sys

    grammar_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/scene_grammar.json")
    rules_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    with open(grammar_path, encoding="utf-8") as f:
        grammar = json.load(f)

    pacing_rules: dict = {}
    if rules_path and rules_path.exists():
        with open(rules_path, encoding="utf-8") as f:
            pacing_rules = json.load(f)

    manifest = run(grammar, pacing_rules)
    errors = validate_timing(manifest, grammar)
    if errors:
        print("ERRORS:", errors)
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
