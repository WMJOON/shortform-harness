"""
eval/runner.py — Template eval_cases 실행기

각 템플릿 YAML의 eval_cases를 읽어 fixture 기준 출력을 검증한다.
"""

from __future__ import annotations

import json
import operator
from pathlib import Path
from typing import Any

import yaml

HARNESS_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = HARNESS_ROOT / "templates"
FIXTURES_DIR = HARNESS_ROOT / "eval" / "fixtures"


def run_all(stage_filter: str | None = None) -> list[dict]:
    results = []
    for template_path in sorted(TEMPLATES_DIR.rglob("*.yaml")):
        with open(template_path, encoding="utf-8") as f:
            template = yaml.safe_load(f)

        stage = template.get("stage", "")
        if stage_filter and stage != stage_filter:
            continue

        for case in template.get("eval_cases", []):
            result = run_case(case, template)
            results.append(result)

    return results


def run_case(case: dict, template: dict) -> dict:
    case_id = case.get("id", "unknown")
    fixture_path = HARNESS_ROOT / case.get("input_fixture", "")

    if not fixture_path.exists():
        return {
            "id": case_id,
            "passed": False,
            "message": f"Fixture not found: {fixture_path}",
        }

    with open(fixture_path, encoding="utf-8") as f:
        fixture = json.load(f)

    # fixture에서 출력을 바로 읽어 expected 조건 검증 (LLM 호출 없이)
    output = fixture.get("expected_output", fixture)
    expected = case.get("expected", {})

    failures = []
    for path_expr, condition in expected.items():
        value = _extract(output, path_expr)
        ok, msg = _check(value, condition)
        if not ok:
            failures.append(f"{path_expr}: {msg} (got {value!r})")

    return {
        "id": case_id,
        "passed": len(failures) == 0,
        "message": "; ".join(failures) if failures else "OK",
    }


def _extract(obj: Any, path: str) -> Any:
    """JSONPath-lite: 'scenes[0].scene_type', 'beats[-1].function' 등."""
    parts = path.replace("[", ".").replace("]", "").split(".")
    current = obj
    for part in parts:
        if part == "":
            continue
        if isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _check(value: Any, condition: Any) -> tuple[bool, str]:
    """condition 딕셔너리 또는 단순 값으로 value를 검증."""
    if not isinstance(condition, dict):
        ok = value == condition
        return ok, f"expected {condition!r}"

    for op, expected in condition.items():
        if op == "eq":
            if value != expected:
                return False, f"expected == {expected}"
        elif op == "lte":
            if not (value is not None and value <= expected):
                return False, f"expected <= {expected}"
        elif op == "gte":
            if not (value is not None and value >= expected):
                return False, f"expected >= {expected}"
        elif op == "not_empty":
            if not value:
                return False, "expected non-empty"
        elif op == "contains":
            if expected not in str(value):
                return False, f"expected to contain '{expected}'"

    return True, "OK"


if __name__ == "__main__":
    results = run_all()
    passed = sum(1 for r in results if r["passed"])
    print(f"Results: {passed}/{len(results)} passed")
    for r in results:
        icon = "✓" if r["passed"] else "✗"
        print(f"  {icon} {r['id']} — {r['message']}")
