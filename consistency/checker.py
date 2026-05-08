"""
consistency/checker.py — Output Consistency + Pipeline Integrity 통합 검사기

각 스테이지 직후 호출되어 property별 일관성과 파이프라인 정합성을 검증한다.
"""

from __future__ import annotations

from pathlib import Path

import yaml

HARNESS_ROOT = Path(__file__).parent.parent
PROPERTIES_CONFIG = HARNESS_ROOT / "consistency" / "properties.yaml"
INTEGRITY_CONFIG = HARNESS_ROOT / "consistency" / "rules" / "pipeline_integrity.yaml"


def check_scene_grammar(scene_grammar: dict) -> list[dict]:
    """Stage 2 직후: schema 수준 이상의 일관성 검사."""
    issues = []
    scenes = scene_grammar.get("scenes", [])
    anchors = scene_grammar.get("consistency_anchors", {})

    # PI002
    if scenes and scenes[0].get("scene_type") != "hook":
        issues.append(_issue("PI002", "error", "scenes[0].scene_type must be 'hook'"))

    # PI003: ppl_present → product_focus 씬 존재
    ppl = scene_grammar.get("narrative", {}).get("ppl_present", False)
    has_product = any(s.get("scene_type") == "product_focus" for s in scenes)
    if ppl and not has_product:
        issues.append(_issue("PI003", "error", "ppl_present=true but no product_focus scene"))

    # consistency_anchors 임베드 검사
    char_desc = anchors.get("character", {}).get("description", "")
    for s in scenes:
        vp = s.get("visual_prompt", "")
        # 최소한 character description의 핵심 단어가 포함돼야 함
        first_word = char_desc.split()[0] if char_desc else ""
        if first_word and first_word.lower() not in vp.lower():
            issues.append(_issue(
                "character.visual", "warning",
                f"scene {s['id']} visual_prompt may be missing character anchor",
            ))
            break  # 첫 번째만 보고

    # PI006: avg 씬 길이 허용범위
    if scenes:
        avg = sum(s.get("duration", 0) for s in scenes) / len(scenes)
        pacing_avg = scene_grammar.get("pacing_avg_hint", 0)
        if pacing_avg and abs(avg - pacing_avg) / pacing_avg > 0.20:
            issues.append(_issue("PI006", "warning", f"avg scene duration {avg:.2f}s deviates >20% from pacing rule"))

    return issues


def check_timing_manifest(timing_manifest: dict, scene_grammar: dict) -> list[dict]:
    """Stage 5 직후: PI004 + 총 길이 검사."""
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
    """Stage 1 직후: PI001 + PI002(beat) 검사."""
    issues = []
    beats = beat_structure.get("beats", [])

    if beats and beats[0].get("function") != "hook":
        issues.append(_issue("PI002", "error", "beats[0].function must be 'hook'"))
    if beats and beats[-1].get("function") != "cta":
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
