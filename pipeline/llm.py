"""pipeline/llm.py — shared LLM call utilities.

백엔드 우선순위 (harness.yaml llm_backend 설정):
  anthropic  → ANTHROPIC_API_KEY  (기본값)
  openai     → OPENAI_API_KEY     (ANTHROPIC_API_KEY 없을 때 자동 fallback)

API 키 없이 실행하려면:
  /harness-run <프롬프트>  ← Claude Code 스킬 사용
"""

from __future__ import annotations

import os

ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL    = "gpt-4o"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def call_llm(system: str, user: str, max_tokens: int = 2048, backend: str | None = None) -> str:
    """LLM을 호출한다. backend가 None이면 사용 가능한 키로 자동 결정."""
    resolved = _resolve_backend() if (not backend or backend == "auto") else backend

    if resolved == "anthropic":
        return _call_anthropic(system, user, max_tokens)
    if resolved == "openai":
        return _call_openai(system, user, max_tokens)

    raise RuntimeError(
        f"LLM 백엔드 '{resolved}'을 사용할 수 없습니다.\n"
        "방법 1: .env에 ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 추가\n"
        "방법 2: Claude Code 스킬 사용 → /harness-run <프롬프트>"
    )


def _resolve_backend() -> str:
    """키가 있는 백엔드를 자동 선택한다. anthropic 우선."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "none"


def _call_anthropic(system: str, user: str, max_tokens: int) -> str:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("pip install anthropic")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def _call_openai(system: str, user: str, max_tokens: int) -> str:
    try:
        import openai
    except ImportError:
        raise RuntimeError("pip install openai")

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content


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
