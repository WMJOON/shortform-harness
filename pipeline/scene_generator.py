"""
pipeline/scene_generator.py — Stage 3: scene_grammar → scene assets (병렬)

각 씬에 대해 generation_request를 생성하고 비주얼 백엔드를 호출한다.
실제 API 호출은 백엔드별 어댑터로 위임한다.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pipeline.loader import resolve_active_template, resolve_active_properties


def run(
    scene_grammar: dict,
    harness: dict,
    output_dir: Path,
    scene_ids: list[int] | None = None,
) -> dict[int, dict]:
    """
    모든 씬(또는 지정 씬)에 대해 generation_request를 생성하고 백엔드 호출.

    Args:
        scene_ids: None이면 전체 씬, 지정 시 해당 씬만 재생성

    Returns:
        {scene_id: {"request": GenerationRequest, "output_path": str}}
    """
    template = resolve_active_template(harness, "scene_generator")
    backend = harness.get("generation", {}).get("visual", "kling")
    anchors = scene_grammar["consistency_anchors"]
    scenes = scene_grammar["scenes"]

    if scene_ids is not None:
        scenes = [s for s in scenes if s["id"] in scene_ids]

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, dict] = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_process_scene, scene, anchors, template, backend, output_dir): scene["id"]
            for scene in scenes
        }
        for future in as_completed(futures):
            scene_id = futures[future]
            try:
                results[scene_id] = future.result()
            except Exception as exc:
                results[scene_id] = {"error": str(exc)}

    return results


def _process_scene(
    scene: dict,
    anchors: dict,
    template: dict,
    backend: str,
    output_dir: Path,
) -> dict:
    """단일 씬 처리: generation_request 생성 → 백엔드 호출."""
    gen_request = _build_generation_request(scene, anchors, template, backend)

    # generation_request 저장 (재사용/디버깅)
    req_path = output_dir / f"scene_{scene['id']:03d}_request.json"
    req_path.write_text(json.dumps(gen_request, ensure_ascii=False, indent=2), encoding="utf-8")

    output_path = _call_backend(gen_request, output_dir)
    return {"request": gen_request, "output_path": str(output_path)}


def _build_generation_request(
    scene: dict,
    anchors: dict,
    template: dict,
    backend: str,
) -> dict:
    """템플릿 렌더링 → LLM 호출 → generation_request JSON 반환."""
    char = anchors.get("character", {})
    bg = anchors.get("background", {})

    vars = {
        "scene.id": scene["id"],
        "scene.scene_type": scene["scene_type"],
        "scene.duration": scene["duration"],
        "scene.camera": scene["camera"],
        "scene.emotion": scene["emotion"],
        "scene.zoom": str(scene.get("zoom", False)).lower(),
        "scene.voiceover": scene.get("voiceover", ""),
        "scene.visual_prompt": scene.get("visual_prompt", ""),
        "consistency_anchors.character.description": char.get("description", ""),
        "consistency_anchors.background.description": bg.get("description", ""),
        "consistency_anchors.background.style": bg.get("style", ""),
        "consistency_anchors.character.negative_prompt": char.get("negative_prompt", ""),
        "generation_backend": backend,
    }

    def render(text: str) -> str:
        for k, v in vars.items():
            text = text.replace(f"{{{{ {k} }}}}", str(v))
        return text

    system_msg = render(template["system"])
    user_msg = render(template["user"])

    raw = _call_llm(system_msg, user_msg)
    return _parse_json(raw)


def _call_llm(system: str, user: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    except ImportError:
        raise RuntimeError("anthropic SDK not installed. Run: pip install anthropic")


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
    return json.loads(text)


def _call_backend(gen_request: dict, output_dir: Path) -> Path:
    """백엔드별 실제 생성 API 호출 (stub — 실제 구현 시 교체)."""
    backend = gen_request.get("backend", "kling")
    scene_id = gen_request.get("scene_id", 0)
    output_path = output_dir / f"scene_{scene_id:03d}.mp4"

    if backend == "kling":
        return _kling_generate(gen_request, output_path)
    elif backend == "gpt_image_2":
        return _gpt_image_2_generate(gen_request, output_path)
    else:
        raise ValueError(f"Unknown backend: {backend}")


def _kling_generate(req: dict, output_path: Path) -> Path:
    """Kling AI image-to-video API 호출 stub."""
    # TODO: Kling API 실제 구현
    # POST https://api.klingai.com/v1/videos/image2video
    raise NotImplementedError("Kling backend not yet implemented")


def _gpt_image_2_generate(req: dict, output_path: Path) -> Path:
    """GPT Image 2 API 호출 stub."""
    # TODO: OpenAI images.generate 실제 구현
    raise NotImplementedError("GPT Image 2 backend not yet implemented")
