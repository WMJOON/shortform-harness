"""pipeline/llm.py — shared LLM call utilities."""

from __future__ import annotations

MODEL = "claude-sonnet-4-6"


def call_llm(system: str, user: str, max_tokens: int = 2048) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")


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
