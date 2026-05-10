"""
cli.py — Shortform Harness CLI

Entry point: `harness` command (via pyproject.toml scripts)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

app = typer.Typer(name="harness", help="Shortform Video Generation Harness")
registry_app = typer.Typer(help="Prompt Registry 관리")
app.add_typer(registry_app, name="registry")

console = Console()
HARNESS_ROOT = Path(__file__).parent


# ── run ───────────────────────────────────────────────────────────────────

@app.command()
def run(
    prompt: str = typer.Argument(..., help="영상 컨셉 (자유 형식)"),
    duration: float = typer.Option(30.0, "--duration", "-d", help="목표 영상 길이 (초)"),
    preset: Optional[str] = typer.Option(None, "--preset", help="preset 이름 (예: lifestyle_kr)"),
    custom: Optional[str] = typer.Option(None, "--custom", help="custom 파일 (예: amyglamy)"),
    resume: Optional[str] = typer.Option(None, "--resume", help="재개할 run_id"),
    from_stage: Optional[str] = typer.Option(None, "--from-stage", help="특정 스테이지부터 시작"),
    chat: bool = typer.Option(False, "--chat", help="오케스트레이터와 대화 모드"),
    dry_run: bool = typer.Option(False, "--dry-run", help="실제 API 호출 없이 계획만 출력"),
):
    """파이프라인 실행."""
    from orchestrator import agent
    from pipeline import loader

    harness = loader.load_harness()
    _apply_overrides(harness, preset, custom)

    if chat:
        _chat_mode(harness, prompt, resume)
        return

    user_msg = _build_run_message(prompt, duration, resume, from_stage, dry_run)

    console.print(f"\n[bold cyan]harness run[/bold cyan] — {prompt[:60]}...")
    console.print(f"  duration: {duration}s  |  backend: {harness.get('generation', {}).get('visual', 'kling')}")
    if resume:
        console.print(f"  resuming: {resume}")

    with console.status("[bold green]Orchestrator 실행 중..."):
        result = agent.run(user_msg, run_id=resume)

    console.print(result)


def _build_run_message(
    prompt: str,
    duration: float,
    resume: Optional[str],
    from_stage: Optional[str],
    dry_run: bool,
) -> str:
    parts = [f'영상을 만들어줘: "{prompt}"', f"목표 길이: {duration}초"]
    if resume:
        parts.append(f"이전 실행 {resume}에서 재개해줘.")
    if from_stage:
        parts.append(f"{from_stage} 단계부터 시작해줘.")
    if dry_run:
        parts.append("실제 생성 API는 호출하지 말고 계획만 보여줘.")
    return "\n".join(parts)


def _apply_overrides(harness: dict, preset: Optional[str], custom: Optional[str]) -> None:
    if preset:
        harness.setdefault("properties", {})["preset"] = f"properties/presets/{preset}.yaml"
    if custom:
        harness.setdefault("properties", {})["custom"] = f"properties/custom/{custom}.yaml"


def _chat_mode(harness: dict, initial_prompt: str, run_id: Optional[str]) -> None:
    from orchestrator import agent, tools as T

    console.print("\n[bold]Orchestrator Chat Mode[/bold] (종료: q 또는 Ctrl+C)\n")
    current_run_id = run_id or T.new_run_id()

    if initial_prompt:
        response = agent.run(initial_prompt, run_id=current_run_id)
        console.print(f"\n[bold green]Orch[/bold green]  {response}\n")

    while True:
        try:
            user_input = typer.prompt("You")
        except (KeyboardInterrupt, typer.Abort):
            console.print("\n[dim]종료[/dim]")
            break

        if user_input.lower() in ("q", "quit", "exit"):
            break

        response = agent.run(user_input, run_id=current_run_id)
        console.print(f"\n[bold green]Orch[/bold green]  {response}\n")


# ── registry ──────────────────────────────────────────────────────────────

@registry_app.command("list")
def registry_list(
    stage: Optional[str] = typer.Option(None, "--stage", "-s"),
    tags: Optional[list[str]] = typer.Option(None, "--tags", "-t"),
    top: int = typer.Option(10, "--top", "-n"),
):
    """저장된 프롬프트 목록 조회."""
    from orchestrator.tools import search_prompts

    entries = search_prompts(stage or "", tags, top)
    if not entries:
        console.print("[dim]저장된 프롬프트가 없습니다.[/dim]")
        return

    table = Table(title="Prompt Registry")
    table.add_column("ID", style="dim")
    table.add_column("Stage")
    table.add_column("Score", justify="right")
    table.add_column("Version")
    table.add_column("Tags")
    table.add_column("Date", style="dim")

    for e in entries:
        table.add_row(
            e.get("id", ""),
            e.get("stage", ""),
            f"{e.get('score', 0):.1f}",
            e.get("template_version", ""),
            " ".join(e.get("tags", [])),
            e.get("created_at", "")[:10],
        )

    console.print(table)


@registry_app.command("save")
def registry_save(
    run_id: str = typer.Option(..., "--run"),
    stage: str = typer.Option(..., "--stage"),
    score: float = typer.Option(..., "--score"),
    tags: list[str] = typer.Option([], "--tags", "-t"),
):
    """실행 결과를 레지스트리에 수동 저장."""
    from orchestrator.tools import save_prompt, load_run_state

    state = load_run_state(run_id)
    stage_data = state.get(stage, {})
    entry_id = save_prompt(
        stage=stage,
        version="v1",
        params=stage_data,
        score=score,
        tags=tags,
        run_id=run_id,
    )
    console.print(f"[green]✓[/green] Saved: {entry_id} (score={score})")


# ── eval ──────────────────────────────────────────────────────────────────

@app.command()
def eval(
    stage: Optional[str] = typer.Option(None, "--stage", help="특정 스테이지만 평가"),
):
    """템플릿 eval_cases 실행."""
    from eval.runner import run_all

    console.print("[bold]Template Eval[/bold]")
    with console.status("평가 중..."):
        results = run_all(stage_filter=stage)

    passed = sum(1 for r in results if r["passed"])
    console.print(f"\n결과: {passed}/{len(results)} passed")
    for r in results:
        icon = "[green]✓[/green]" if r["passed"] else "[red]✗[/red]"
        console.print(f"  {icon} {r['id']} — {r.get('message', '')}")


if __name__ == "__main__":
    app()
