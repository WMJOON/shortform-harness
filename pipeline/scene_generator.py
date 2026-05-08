"""pipeline/scene_generator.py — Stage 3: scene_grammar → scene assets (병렬)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.llm import call_llm, strip_code_fence, render_messages
from pipeline.loader import resolve_active_template


def run(
    scene_grammar: dict,
    harness: dict,
    output_dir: Path,
    scene_ids: list[int] | None = None,
) -> dict[int, dict]:
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
    gen_request = _build_generation_request(scene, anchors, template, backend)

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
    char = anchors.get("character", {})
    bg = anchors.get("background", {})

    system, user = render_messages(template, {
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
    })
    return json.loads(strip_code_fence(call_llm(system, user, max_tokens=1024)))


def _call_backend(gen_request: dict, output_dir: Path) -> Path:
    backend = gen_request.get("backend", "kling")
    scene_id = gen_request.get("scene_id", 0)
    output_path = output_dir / f"scene_{scene_id:03d}.mp4"

    if backend == "kling":
        return _kling_generate(gen_request, output_path)
    elif backend == "gpt_image_2":
        return _gpt_image_2_generate(gen_request, output_path)
    raise ValueError(f"Unknown backend: {backend}")


def _kling_generate(req: dict, output_path: Path) -> Path:
    raise NotImplementedError("Kling backend not yet implemented")


def _gpt_image_2_generate(req: dict, output_path: Path) -> Path:
    raise NotImplementedError("GPT Image 2 backend not yet implemented")
