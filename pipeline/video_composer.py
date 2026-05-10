"""
pipeline/video_composer.py — Stage 6: timing_manifest + scene assets → 최종 MP4

ffmpeg를 사용해 씬 클립을 연결하고 자막, BGM을 합성한다.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def run(
    timing_manifest: dict,
    scene_grammar: dict,
    assets_dir: Path,
    output_path: Path,
    harness: dict,
) -> Path:
    """
    timing_manifest의 씬 순서대로 ffmpeg concat → 자막 burn-in → BGM 믹싱.

    Returns:
        output_path (완성된 MP4)
    """
    composer_cfg = harness.get("stages", {}).get("video_composer", {})
    resolution = composer_cfg.get("resolution", "1080x1920")
    fps = composer_cfg.get("fps", 30)

    # 씬 클립 목록 확인
    scene_clips = _collect_clips(timing_manifest, assets_dir)

    # concat list 파일 생성
    concat_list = assets_dir / "concat_list.txt"
    _write_concat_list(concat_list, scene_clips)

    # 1단계: concat
    raw_output = output_path.with_suffix(".raw.mp4")
    _ffmpeg_concat(concat_list, raw_output, resolution, fps)

    # 2단계: 자막 burn-in (SRT 있을 때만)
    srt_path = assets_dir / "subtitles" / "combined.srt"
    if srt_path.exists():
        subtitled = output_path.with_suffix(".sub.mp4")
        _ffmpeg_burn_subtitles(raw_output, srt_path, subtitled)
        raw_output = subtitled

    # 3단계: BGM 믹싱 (BGM 트랙 있을 때만)
    bgm_track = timing_manifest.get("bgm_track", "")
    bgm_path = Path(bgm_track) if bgm_track else None
    if bgm_path and bgm_path.exists():
        _ffmpeg_mix_bgm(raw_output, bgm_path, timing_manifest, output_path)
    else:
        raw_output.rename(output_path)

    return output_path


def _collect_clips(timing_manifest: dict, assets_dir: Path) -> list[Path]:
    clips = []
    for sc in timing_manifest["scenes"]:
        clip = assets_dir / f"scene_{sc['id']:03d}.mp4"
        if not clip.exists():
            raise FileNotFoundError(f"Scene clip not found: {clip}")
        clips.append(clip)
    return clips


def _write_concat_list(path: Path, clips: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"file '{clip.resolve()}'" for clip in clips]
    path.write_text("\n".join(lines), encoding="utf-8")


def _ffmpeg_concat(concat_list: Path, output: Path, resolution: str, fps: int) -> None:
    w, h = resolution.split("x")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-vf", f"scale={w}:{h},fps={fps}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac",
        str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _ffmpeg_burn_subtitles(video: Path, srt: Path, output: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-vf", f"subtitles={srt}",
        "-c:a", "copy",
        str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _ffmpeg_mix_bgm(
    video: Path,
    bgm: Path,
    timing_manifest: dict,
    output: Path,
) -> None:
    total = timing_manifest["total_duration_sec"]
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(bgm),
        "-filter_complex",
        f"[1:a]volume=0.3,atrim=0:{total}[bgm];[0:a][bgm]amix=inputs=2:duration=first[out]",
        "-map", "0:v", "-map", "[out]",
        "-c:v", "copy", "-c:a", "aac",
        str(output),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
