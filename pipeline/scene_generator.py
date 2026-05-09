"""pipeline/scene_generator.py — Stage 3: scene_grammar → scene assets (병렬).

인물 일관성 전략:
  1. generate_character_ref() — 캐릭터 레퍼런스 이미지 1장 생성 (run당 1회)
  2. _gpt_image_2_generate() — Responses API에 ref 이미지 + 씬 프롬프트 전달
     → 같은 인물로 씬별 구도·상황만 다르게 생성
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

from pipeline.llm import call_llm, strip_code_fence, render_messages
from pipeline.loader import resolve_active_template

load_dotenv()


def generate_character_ref(
    anchors: dict,
    output_dir: Path,
    visual_model: str = "gpt-image-1",
) -> Path | None:
    """캐릭터 레퍼런스 이미지를 생성한다. 이미 있으면 재사용."""
    import openai

    ref_path = output_dir / "character_ref.png"
    if ref_path.exists():
        return ref_path

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    char = anchors.get("character", {})
    bg   = anchors.get("background", {})
    prompt = (
        f"Full portrait, frontal pose, centered. "
        f"{char.get('description', '')}. "
        f"Background: {bg.get('description', '')}. "
        f"Photorealistic, vertical composition, soft natural lighting. "
        f"Negative: {char.get('negative_prompt', '')}."
    )

    client = openai.OpenAI(api_key=api_key)
    resp = client.images.generate(
        model=visual_model,
        prompt=prompt,
        size="1024x1536",
        quality="high",
        n=1,
    )
    img_bytes = base64.b64decode(resp.data[0].b64_json)
    ref_path.write_bytes(img_bytes)
    return ref_path


def run(
    scene_grammar: dict,
    harness: dict,
    output_dir: Path,
    scene_ids: list[int] | None = None,
) -> dict[int, dict]:
    template = resolve_active_template(harness, "scene_generator")
    backend  = harness.get("generation", {}).get("visual", "kling")
    anchors  = scene_grammar["consistency_anchors"]
    scenes   = scene_grammar["scenes"]

    if scene_ids is not None:
        scenes = [s for s in scenes if s["id"] in scene_ids]

    output_dir.mkdir(parents=True, exist_ok=True)
    visual_model = harness.get("generation", {}).get("visual_model", "gpt-image-1")

    # 레퍼런스 이미지 선생성 (gpt_image_2 백엔드일 때만)
    char_ref: Path | None = None
    if backend == "gpt_image_2":
        char_ref = generate_character_ref(anchors, output_dir, visual_model)
        if char_ref:
            print(f"  ✓ character_ref: {char_ref.name}")

    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                _process_scene, scene, anchors, template, backend, visual_model, char_ref, output_dir
            ): scene["id"]
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
    visual_model: str,
    char_ref: Path | None,
    output_dir: Path,
) -> dict:
    gen_request = _build_generation_request(scene, anchors, template, backend)
    gen_request["visual_model"] = visual_model
    gen_request["char_ref"] = str(char_ref) if char_ref else None

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
    bg   = anchors.get("background", {})

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
    backend    = gen_request.get("backend", "kling")
    scene_id   = gen_request.get("scene_id", 0)
    output_path = output_dir / f"scene_{scene_id:03d}.mp4"

    if backend == "kling":
        return _kling_generate(gen_request, output_path)
    elif backend == "gpt_image_2":
        return _gpt_image_2_generate(gen_request, output_path)
    raise ValueError(f"Unknown backend: {backend}")


def _kling_generate(req: dict, output_path: Path) -> Path:
    raise NotImplementedError("Kling backend not yet implemented")


def _gpt_image_2_generate(req: dict, output_path: Path) -> Path:
    """gpt-image-1으로 씬 이미지 생성.

    character_ref.png가 있으면 Responses API로 인물 일관성 유지.
    없으면 images.generate() 단독 사용.
    """
    import openai

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 없습니다.")

    client       = openai.OpenAI(api_key=api_key)
    prompt       = req.get("final_prompt", req.get("visual_prompt", ""))
    duration     = req.get("duration", 3.0)
    visual_model = req.get("visual_model", "gpt-image-1")
    char_ref_path = req.get("char_ref")

    if char_ref_path and Path(char_ref_path).exists():
        # images.edit() — 레퍼런스 이미지 기반으로 인물 일관성 유지
        edit_prompt = (
            f"Same person as in the reference image, new scene: {prompt}. "
            f"Keep face, hair, skin tone, body type identical. "
            f"Only change pose, expression, background, and situation."
        )
        with open(char_ref_path, "rb") as ref_f:
            resp = client.images.edit(
                model=visual_model,
                image=ref_f,
                prompt=edit_prompt[:4000],
                size="1024x1536",
                n=1,
            )
        img_b64 = resp.data[0].b64_json
    else:
        # 레퍼런스 없으면 단독 생성
        resp = client.images.generate(
            model=visual_model,
            prompt=prompt,
            size="1024x1536",
            quality="medium",
            n=1,
        )
        img_b64 = resp.data[0].b64_json

    img_path = output_path.with_suffix(".png")
    img_path.write_bytes(base64.b64decode(img_b64))

    subprocess.run([
        "ffmpeg", "-y", "-loop", "1",
        "-i", str(img_path),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-t", str(duration),
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        str(output_path),
    ], check=True, capture_output=True)

    img_path.unlink()
    return output_path
