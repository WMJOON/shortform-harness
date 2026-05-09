"""pipeline/llm.py — shared LLM call utilities.

실제 파이프라인에서 LLM 스테이지(Stage 1·2)는 Claude Code 스킬로 직접 실행한다.
이 모듈은 스크립트 단독 실행 시 또는 Anthropic API를 직접 호출할 때만 사용한다.

API 키 없이 실행하려면:
  /harness-run <프롬프트>  ← Claude Code 스킬 사용 (ANTHROPIC_API_KEY 불필요)
"""

from __future__ import annotations

import os

MODEL = "claude-sonnet-4-6"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 미설치 시 환경변수는 이미 설정된 값 사용


def call_llm(system: str, user: str, max_tokens: int = 2048) -> str:
    """Anthropic API를 직접 호출한다.

    API 키 없이 실행하려면 이 함수 대신 Claude Code 스킬을 사용한다:
      /harness-run <프롬프트>
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY가 없습니다.\n"
            "방법 1: .env 파일에 ANTHROPIC_API_KEY=sk-... 추가\n"
            "방법 2: Claude Code 스킬로 실행 → /harness-run <프롬프트>"
        )

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    return text


def render_messages(template: dict, vars: dict) -> tuple[str, str]:
    """Render (system, user) strings from template + variable dict."""
    def _r(text: str) -> str:
        for k, v in vars.items():
            text = text.replace(f"{{{{ {k} }}}}", str(v))
        return text
    return _r(template["system"]), _r(template["user"])
