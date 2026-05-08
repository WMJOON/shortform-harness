"""
orchestrator/agent.py — LLM Orchestrator Agent

사용자 요청을 받아 6단계 파이프라인을 도구 호출로 실행하는 에이전트.
tool_use 루프를 직접 구현 — anthropic SDK 사용.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator import tools as T

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"

TOOL_DEFINITIONS = [
    {
        "name": "run_story_parser",
        "description": "Stage 1: 사용자 프롬프트 → beat_structure JSON",
        "input_schema": {
            "type": "object",
            "required": ["prompt", "duration"],
            "properties": {
                "prompt": {"type": "string"},
                "duration": {"type": "number"},
            },
        },
    },
    {
        "name": "run_scene_planner",
        "description": "Stage 2: beat_structure → scene_grammar JSON",
        "input_schema": {
            "type": "object",
            "required": ["beat_structure"],
            "properties": {
                "beat_structure": {"type": "object"},
            },
        },
    },
    {
        "name": "run_scene_generator",
        "description": "Stage 3: scene_grammar → 씬별 비주얼 생성 (병렬). scene_ids 미지정 시 전체 씬.",
        "input_schema": {
            "type": "object",
            "required": ["scene_grammar", "run_id"],
            "properties": {
                "scene_grammar": {"type": "object"},
                "run_id": {"type": "string"},
                "scene_ids": {"type": "array", "items": {"type": "integer"}},
            },
        },
    },
    {
        "name": "run_subtitle_generator",
        "description": "Stage 4: scene_grammar → subtitle_tracks",
        "input_schema": {
            "type": "object",
            "required": ["scene_grammar"],
            "properties": {
                "scene_grammar": {"type": "object"},
                "use_llm": {"type": "boolean"},
            },
        },
    },
    {
        "name": "run_pacing_engine",
        "description": "Stage 5: scene_grammar → timing_manifest (rule-based, 결정론적)",
        "input_schema": {
            "type": "object",
            "required": ["scene_grammar"],
            "properties": {
                "scene_grammar": {"type": "object"},
            },
        },
    },
    {
        "name": "run_video_composer",
        "description": "Stage 6: timing_manifest + assets → 최종 MP4",
        "input_schema": {
            "type": "object",
            "required": ["timing_manifest", "scene_grammar", "run_id"],
            "properties": {
                "timing_manifest": {"type": "object"},
                "scene_grammar": {"type": "object"},
                "run_id": {"type": "string"},
            },
        },
    },
    {
        "name": "save_run_state",
        "description": "현재 스테이지 결과를 run_state.json에 저장 (재개 가능)",
        "input_schema": {
            "type": "object",
            "required": ["run_id", "stage", "data"],
            "properties": {
                "run_id": {"type": "string"},
                "stage": {"type": "string"},
                "data": {"type": "object"},
            },
        },
    },
    {
        "name": "load_run_state",
        "description": "이전 실행 상태 로드",
        "input_schema": {
            "type": "object",
            "required": ["run_id"],
            "properties": {
                "run_id": {"type": "string"},
            },
        },
    },
    {
        "name": "search_prompts",
        "description": "레지스트리에서 고점수 프롬프트 검색",
        "input_schema": {
            "type": "object",
            "required": ["stage"],
            "properties": {
                "stage": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer"},
            },
        },
    },
    {
        "name": "save_prompt",
        "description": "실행 결과를 레지스트리에 저장",
        "input_schema": {
            "type": "object",
            "required": ["stage", "version", "params", "score", "tags"],
            "properties": {
                "stage": {"type": "string"},
                "version": {"type": "string"},
                "params": {"type": "object"},
                "score": {"type": "number"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "run_id": {"type": "string"},
            },
        },
    },
    {
        "name": "check_consistency",
        "description": "scene_grammar의 property별 출력 일관성 검사",
        "input_schema": {
            "type": "object",
            "required": ["scene_grammar"],
            "properties": {
                "scene_grammar": {"type": "object"},
            },
        },
    },
    {
        "name": "check_pipeline_integrity",
        "description": "PI001-PI006 규칙 검사",
        "input_schema": {
            "type": "object",
            "properties": {
                "beat_structure": {"type": "object"},
                "scene_grammar": {"type": "object"},
                "timing_manifest": {"type": "object"},
            },
        },
    },
]

TOOL_DISPATCH: dict[str, Any] = {
    "run_story_parser":        T.run_story_parser,
    "run_scene_planner":       T.run_scene_planner,
    "run_scene_generator":     T.run_scene_generator,
    "run_subtitle_generator":  T.run_subtitle_generator,
    "run_pacing_engine":       T.run_pacing_engine,
    "run_video_composer":      T.run_video_composer,
    "save_run_state":          T.save_run_state,
    "load_run_state":          T.load_run_state,
    "search_prompts":          T.search_prompts,
    "save_prompt":             T.save_prompt,
    "check_consistency":       T.check_consistency,
    "check_pipeline_integrity": T.check_pipeline_integrity,
}


def run(user_message: str, run_id: str | None = None, max_turns: int = 30) -> str:
    """
    오케스트레이터 에이전트 실행.

    Args:
        user_message: 사용자 요청
        run_id: 기존 실행 재개 시 지정
    Returns:
        최종 에이전트 응답 텍스트
    """
    import anthropic

    client = anthropic.Anthropic()
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

    if run_id:
        context = f"[Resuming run_id: {run_id}]\n\n{user_message}"
    else:
        run_id = T.new_run_id()
        context = f"[New run_id: {run_id}]\n\n{user_message}"

    messages = [{"role": "user", "content": context}]

    for _ in range(max_turns):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(text_blocks)

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = _invoke_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
            messages.append({"role": "user", "content": tool_results})

    return "[max_turns reached]"


def _invoke_tool(name: str, inputs: dict) -> Any:
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(**inputs)
    except Exception as exc:
        return {"error": str(exc), "tool": name}
