"""eval/runner.py — Template eval_cases 실행기."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

# standalone 스크립트 실행 시 프로젝트 루트를 sys.path에 추가
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

HARNESS_ROOT = _ROOT
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
    """JSONPath-lite: 'scenes[0].scene_type', 'beats[-1].function', 'sum(beats[*].duration_ratio)' 등."""
    # sum() 집계 처리: sum(arr[*].field) 또는 sum(arr[].field)
    if path.startswith("sum(") and path.endswith(")"):
        inner = path[4:-1]  # e.g. beats[*].duration_ratio
        # 마지막 .field 분리
        if "." in inner:
            arr_path, field = inner.rsplit(".", 1)
        else:
            return None
        # [*] 또는 [] 제거해 배열 경로 추출
        arr_path_clean = arr_path.replace("[*]", "").replace("[]", "")
        arr = _extract(obj, arr_path_clean)
        if not isinstance(arr, list):
            return None
        return round(sum(item.get(field, 0) for item in arr if isinstance(item, dict)), 6)

    parts = path.replace("[", ".").replace("]", "").split(".")
    current = obj
    for part in parts:
        if part == "" or part == "*":
            continue
        # "length" 키워드 → 배열/문자열 길이
        if part == "length":
            if isinstance(current, (list, str)):
                current = len(current)
            else:
                return None
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
    """condition 딕셔너리 또는 단순 값으로 value를 검증.

    String인 expected 값(path 참조/표현식)은 런타임 컨텍스트 없이 평가 불가 → skip.
    tolerance 키는 eq의 근사 허용 범위로 처리.
    """
    if not isinstance(condition, dict):
        ok = value == condition
        return ok, f"expected {condition!r}"

    tolerance = condition.get("tolerance")

    for op, expected in condition.items():
        if op == "tolerance":
            continue
        # string 레퍼런스/표현식(숫자/bool이 아님) → 런타임 평가 불가, skip
        if isinstance(expected, str) and op in ("eq", "lte", "gte"):
            continue
        if op == "eq":
            if tolerance is not None:
                if value is None or abs(value - expected) > tolerance:
                    return False, f"expected {expected} ±{tolerance} (got {value})"
            else:
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
