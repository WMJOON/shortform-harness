"""consistency/checker.py — Output Consistency + Pipeline Integrity 통합 검사기."""

from __future__ import annotations

from pipeline.loader import HARNESS_ROOT
from pipeline.constants import SceneType, BeatFunction


def check_scene_grammar(scene_grammar: dict) -> list[dict]:
    issues = []
    scenes = scene_grammar.get("scenes", [])
    anchors = scene_grammar.get("consistency_anchors", {})

    if scenes and scenes[0].get("scene_type") != SceneType.HOOK:
        issues.append(_issue("PI002", "error", "scenes[0].scene_type must be 'hook'"))

    ppl = scene_grammar.get("narrative", {}).get("ppl_present", False)
    has_product = any(s.get("scene_type") == SceneType.PRODUCT_FOCUS for s in scenes)
    if ppl and not has_product:
        issues.append(_issue("PI003", "error", "ppl_present=true but no product_focus scene"))

    char_desc = anchors.get("character", {}).get("description", "")
    first_word = char_desc.split()[0] if char_desc else ""
    if first_word:
        for s in scenes:
            if first_word.lower() not in s.get("visual_prompt", "").lower():
                issues.append(_issue("character.visual", "warning",
                    f"scene {s['id']} visual_prompt may be missing character anchor"))
                break

    pacing_avg = scene_grammar.get("pacing_avg_hint", 0)
    if scenes and pacing_avg:
        avg = sum(s.get("duration", 0) for s in scenes) / len(scenes)
        if abs(avg - pacing_avg) / pacing_avg > 0.20:
            issues.append(_issue("PI006", "warning", f"avg scene duration {avg:.2f}s deviates >20% from pacing rule"))

    return issues


def check_timing_manifest(timing_manifest: dict, scene_grammar: dict) -> list[dict]:
    issues = []

    grammar_count = len(scene_grammar.get("scenes", []))
    timing_count = len(timing_manifest.get("scenes", []))
    if grammar_count != timing_count:
        issues.append(_issue(
            "PI004", "error",
            f"scene count mismatch: grammar={grammar_count}, timing={timing_count}",
        ))

    total = timing_manifest.get("total_duration_sec", 0)
    actual_end = timing_manifest["scenes"][-1]["end_sec"] if timing_manifest.get("scenes") else 0.0
    if abs(actual_end - total) > 0.5:
        issues.append(_issue(
            "timing.total", "error",
            f"total_duration={total}s but last scene ends at {actual_end:.3f}s",
        ))

    return issues


def check_beat_structure(beat_structure: dict) -> list[dict]:
    issues = []
    beats = beat_structure.get("beats", [])

    if beats and beats[0].get("function") != BeatFunction.HOOK:
        issues.append(_issue("PI002", "error", "beats[0].function must be 'hook'"))
    if beats and beats[-1].get("function") != BeatFunction.CTA:
        issues.append(_issue("PI002", "error", "beats[-1].function must be 'cta'"))

    ratio_sum = sum(b.get("duration_ratio", 0) for b in beats)
    if abs(ratio_sum - 1.0) > 0.01:
        issues.append(_issue("PI001", "error", f"duration_ratio sum={ratio_sum:.4f} ≠ 1.0"))

    return issues


def _issue(rule_id: str, severity: str, message: str) -> dict:
    return {"rule": rule_id, "severity": severity, "message": message}


def summarize(issues: list[dict]) -> str:
    if not issues:
        return "✓ All checks passed"
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    lines = []
    if errors:
        lines.append(f"✗ {len(errors)} error(s):")
        lines.extend(f"  [{i['rule']}] {i['message']}" for i in errors)
    if warnings:
        lines.append(f"⚠ {len(warnings)} warning(s):")
        lines.extend(f"  [{i['rule']}] {i['message']}" for i in warnings)
    return "\n".join(lines)
