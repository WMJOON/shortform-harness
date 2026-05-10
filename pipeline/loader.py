"""
pipeline/loader.py — harness.yaml → active 템플릿 + properties 로드

loader.py는 harness.yaml을 읽어 각 스테이지에서 사용할
활성 템플릿 경로, pacing_rules, active_properties를 결합해 반환한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


HARNESS_ROOT = Path(__file__).parent.parent


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_harness(harness_path: Path | None = None) -> dict:
    path = harness_path or HARNESS_ROOT / "harness.yaml"
    return _load_yaml(path)


def resolve_active_template(harness: dict, stage: str) -> dict:
    """stage 이름으로 활성 템플릿 YAML을 반환."""
    stage_cfg = harness["stages"].get(stage, {})
    active_version = stage_cfg.get("active")
    if not active_version:
        raise ValueError(f"No active template for stage: {stage}")
    template_path = HARNESS_ROOT / stage_cfg["candidates"][active_version]
    return _load_yaml(template_path)


def resolve_pacing_rules(harness: dict) -> dict:
    """harness.yaml의 pacing_engine.pacing_rules 반환."""
    return harness.get("stages", {}).get("pacing_engine", {}).get("pacing_rules", {})


def resolve_active_properties(harness: dict) -> dict:
    """preset + custom을 병합한 active_properties 딕셔너리 반환."""
    prop_cfg = harness.get("properties", {})
    preset_path = HARNESS_ROOT / prop_cfg.get("preset", "")
    custom_path = HARNESS_ROOT / prop_cfg.get("custom", "")

    preset = _load_yaml(preset_path) if preset_path.exists() else {}
    custom = _load_yaml(custom_path) if custom_path.exists() else {}

    # preset defaults + custom overrides 병합
    active: dict[str, Any] = {}
    active.update(preset.get("defaults", {}))
    for key, val in custom.get("overrides", {}).items():
        active[key] = val.get("value", active.get(key))

    # style_profile_defaults (custom에서 제공하는 기본 캐릭터/배경 등)
    style_defaults = custom.get("style_profile_defaults", {})

    return {
        "values": active,
        "style_profile": style_defaults,
        "active_keys": preset.get("active_properties", []) + custom.get("add_properties", []),
    }


def load_style_profile(run_dir: Path | None = None) -> dict:
    """data/style_profile.json 로드 (없으면 custom.style_profile_defaults 사용)."""
    profile_path = HARNESS_ROOT / "data" / "style_profile.json"
    if profile_path.exists():
        with open(profile_path, encoding="utf-8") as f:
            return json.load(f)
    return {}
