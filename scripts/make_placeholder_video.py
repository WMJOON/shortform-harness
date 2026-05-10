"""
scripts/make_placeholder_video.py
scene_grammar.json + timing_manifest.json → placeholder MP4

실제 비주얼 생성 API 없이 씬별 색상 프레임 + 자막으로 30초 9:16 영상 생성.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── 설정 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
W, H = 1080, 1920
FPS  = 30

SCENE_COLORS = {
    "hook":          ((30,  30,  30),  (255, 80,  120)),   # 어두운 배경, 핑크 강조
    "empathy":       ((45,  35,  55),  (255, 180, 140)),   # 보라 배경, 피치 강조
    "tip":           ((20,  40,  60),  (100, 220, 255)),   # 네이비 배경, 시안 강조
    "product_focus": ((50,  45,  35),  (255, 215, 100)),   # 다크 올리브, 골드 강조
    "cta":           ((40,  20,  20),  (255, 100,  80)),   # 다크 레드, 코랄 강조
    "reaction":      ((30,  50,  40),  (120, 255, 160)),   # 다크 그린, 민트 강조
}

# 한국어 폰트 경로 (macOS 기본)
KR_FONTS = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/NanumGothic.ttf",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in KR_FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_scene_frame(scene: dict, frame_num: int, total_frames: int) -> Image.Image:
    scene_type = scene["scene_type"]
    bg_color, accent = SCENE_COLORS.get(scene_type, ((30, 30, 30), (200, 200, 200)))

    img = Image.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)

    # 상단 그라디언트 효과 (단순 직사각형으로 근사)
    for y in range(300):
        alpha = y / 300
        r = int(bg_color[0] + (accent[0] - bg_color[0]) * (1 - alpha) * 0.3)
        g = int(bg_color[1] + (accent[1] - bg_color[1]) * (1 - alpha) * 0.3)
        b = int(bg_color[2] + (accent[2] - bg_color[2]) * (1 - alpha) * 0.3)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 씬 타입 뱃지 (상단)
    badge_font = get_font(48)
    badge_text = f"[ {scene_type.upper().replace('_', ' ')} ]"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw = bbox[2] - bbox[0]
    draw.rectangle([(W//2 - bw//2 - 20, 100), (W//2 + bw//2 + 20, 180)],
                   fill=accent, outline=None)
    draw.text((W//2 - bw//2, 108), badge_text, font=badge_font, fill=bg_color)

    # Scene ID + 타임라인
    id_font = get_font(36)
    draw.text((60, 220), f"Scene {scene['id']}  ·  {scene['duration']}s",
              font=id_font, fill=(180, 180, 180))

    # 진행 바
    bar_y = 280
    bar_w = W - 120
    progress = frame_num / max(total_frames - 1, 1)
    draw.rectangle([(60, bar_y), (60 + bar_w, bar_y + 6)], fill=(60, 60, 60))
    draw.rectangle([(60, bar_y), (60 + int(bar_w * progress), bar_y + 6)], fill=accent)

    # 중앙 이모지 아이콘 영역 (씬 타입별)
    icons = {"hook": "◉", "empathy": "♡", "tip": "✦", "product_focus": "◈", "cta": "→", "reaction": "◎"}
    icon_font = get_font(200)
    icon = icons.get(scene_type, "●")
    bbox = draw.textbbox((0, 0), icon, font=icon_font)
    iw = bbox[2] - bbox[0]
    draw.text((W//2 - iw//2, H//2 - 200), icon,
              font=icon_font, fill=(*accent, 60))

    # voiceover 텍스트 (중앙)
    vo = scene.get("voiceover", "")
    vo_font = get_font(52)
    lines = textwrap.wrap(vo, width=18)
    y_start = H//2 + 80
    for line in lines[:4]:
        bbox = draw.textbbox((0, 0), line, font=vo_font)
        lw = bbox[2] - bbox[0]
        # 텍스트 그림자
        draw.text((W//2 - lw//2 + 2, y_start + 2), line, font=vo_font, fill=(0, 0, 0))
        draw.text((W//2 - lw//2, y_start), line, font=vo_font, fill=(255, 255, 255))
        y_start += 70

    # 하단 자막 영역 (실제 자막 스타일)
    sub_bg_y = H - 260
    draw.rectangle([(0, sub_bg_y), (W, H)], fill=(0, 0, 0, 0))

    camera_font = get_font(34)
    cam_text = f"📷 {scene['camera']}  |  zoom={'ON' if scene.get('zoom') else 'OFF'}"
    draw.text((60, H - 200), cam_text, font=camera_font, fill=(140, 140, 140))

    emotion_font = get_font(34)
    draw.text((60, H - 150), f"emotion: {scene['emotion']}", font=emotion_font, fill=(140, 140, 140))

    # 하단 자막 (실제 voiceover 앞부분)
    sub_font = get_font(56)
    sub_text = vo[:20] + ("…" if len(vo) > 20 else "")
    bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = bbox[2] - bbox[0]
    # 강조 배경
    draw.rectangle([(W//2 - sw//2 - 16, H - 96), (W//2 + sw//2 + 16, H - 24)],
                   fill=accent)
    draw.text((W//2 - sw//2, H - 92), sub_text, font=sub_font, fill=bg_color)

    return img


def make_scene_clip(scene: dict, output_path: Path) -> None:
    """씬 이미지를 ffmpeg로 비디오 클립으로 변환."""
    duration = scene["duration"]
    total_frames = max(1, int(duration * FPS))

    frames_dir = output_path.parent / f"frames_scene{scene['id']:03d}"
    frames_dir.mkdir(exist_ok=True)

    # 첫 프레임과 마지막 프레임만 생성 (중간은 ffmpeg가 보간)
    for i in [0, total_frames - 1]:
        frame = draw_scene_frame(scene, i, total_frames)
        frame.save(frames_dir / f"frame_{i:06d}.png")

    # 첫 프레임으로 전체 클립 생성 (static)
    first_frame = frames_dir / "frame_000000.png"
    transition = scene.get("transition_out", "cut")

    # zoom 효과
    vf = "scale=1080:1920"
    if scene.get("zoom"):
        # 줌인 효과
        vf = f"scale=1188:2112,zoompan=z='min(zoom+0.0015,1.1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920:fps={FPS}"

    cmd = [
        "ffmpeg", "-y", "-loop", "1",
        "-i", str(first_frame),
        "-vf", vf,
        "-t", str(duration),
        "-r", str(FPS),
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"  ffmpeg error: {result.stderr.decode()[:200]}")
    else:
        print(f"  ✓ scene {scene['id']} clip: {output_path.name} ({duration}s)")

    # 임시 프레임 정리
    import shutil
    shutil.rmtree(frames_dir, ignore_errors=True)


def main(run_id: str) -> None:
    run_dir   = ROOT / "data" / "runs" / run_id
    assets_dir = ROOT / "assets" / run_id
    assets_dir.mkdir(parents=True, exist_ok=True)

    grammar  = json.loads((run_dir / "scene_grammar.json").read_text())
    manifest = json.loads((run_dir / "timing_manifest.json").read_text())

    print(f"\n📹 Placeholder video generation — {run_id}")
    print(f"   {len(grammar['scenes'])} scenes  ·  {grammar['narrative']['total_duration_sec']}s  ·  1080×1920\n")

    # Stage 3: 씬별 클립 생성
    print("Stage 3: Scene clips")
    clip_paths = []
    for scene in grammar["scenes"]:
        clip_path = assets_dir / f"scene_{scene['id']:03d}.mp4"
        make_scene_clip(scene, clip_path)
        clip_paths.append(clip_path)

    # Stage 4: 자막 SRT 생성 (실제 subtitle_timing 사용)
    print("\nStage 4: Subtitle SRT")
    subtitles_dir = assets_dir / "subtitles"
    subtitles_dir.mkdir(exist_ok=True)

    from pipeline.subtitle_generator import run as subtitle_run
    from pipeline.loader import load_harness
    harness = load_harness()
    tracks = subtitle_run(grammar, harness, use_llm=False)

    # 전체 SRT 생성 (절대 타임스탬프)
    scene_start_ms = {sc["id"]: int(sc["start_sec"] * 1000) for sc in manifest["scenes"]}
    srt_lines = []
    srt_idx = 1
    for track in tracks:
        sid = track["scene_id"]
        offset = scene_start_ms.get(sid, 0)
        for sub in track["subtitle_timing"]:
            start_ms = offset + sub["start_ms"]
            end_ms   = offset + sub["end_ms"]
            srt_lines.append(f"{srt_idx}")
            srt_lines.append(f"{_ms_to_srt(start_ms)} --> {_ms_to_srt(end_ms)}")
            srt_lines.append(sub["text"])
            srt_lines.append("")
            srt_idx += 1

    srt_path = subtitles_dir / "combined.srt"
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"  ✓ {srt_idx - 1} subtitle entries → {srt_path.name}")

    # Stage 5 결과 확인 (이미 생성됨)
    print("\nStage 5: Pacing Engine (already done)")
    print(f"  ✓ timing_manifest.json loaded")

    # Stage 6: ffmpeg concat + 자막 burn-in
    print("\nStage 6: Video Composer")
    concat_list = assets_dir / "concat_list.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clip_paths),
        encoding="utf-8"
    )

    raw_mp4   = assets_dir / "raw.mp4"
    final_mp4 = ROOT / "outputs" / f"{run_id}.mp4"
    final_mp4.parent.mkdir(exist_ok=True)

    # concat
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(raw_mp4),
    ], check=True, capture_output=True)
    print(f"  ✓ concat → raw.mp4")

    # 자막 burn-in (한국어 폰트)
    font_path = next((f for f in KR_FONTS if Path(f).exists()), None)
    if font_path:
        subtitle_filter = (
            f"subtitles={srt_path}:force_style='"
            f"Fontname=Apple SD Gothic Neo,"
            f"FontSize=22,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,Outline=2,"
            f"Alignment=2,MarginV=60'"
        )
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", str(raw_mp4),
            "-vf", subtitle_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy",
            str(final_mp4),
        ], capture_output=True)
        if result.returncode == 0:
            print(f"  ✓ 자막 burn-in 완료")
        else:
            # 자막 실패 시 raw 그대로 복사
            import shutil
            shutil.copy(raw_mp4, final_mp4)
            print(f"  ⚠ 자막 burn-in 실패 → raw 사용")
    else:
        import shutil
        shutil.copy(raw_mp4, final_mp4)

    size_mb = final_mp4.stat().st_size / 1024 / 1024
    print(f"\n✅ 완료: {final_mp4}")
    print(f"   크기: {size_mb:.1f} MB  ·  30s  ·  1080×1920")


def _ms_to_srt(ms: int) -> str:
    h  = ms // 3_600_000
    m  = (ms % 3_600_000) // 60_000
    s  = (ms % 60_000) // 1_000
    ms = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "run_20260509_001"
    sys.path.insert(0, str(ROOT))
    main(run_id)
