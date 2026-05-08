# Shortform Video Generation Harness — System Spec

> version: 0.3.0  
> status: draft  
> date: 2026-05-08

---

## 0. Overview

텍스트 프롬프트 하나를 받아 레퍼런스 숏폼 영상의 스타일을 따르는 숏폼 영상을 생성하는 재사용 가능한 파이프라인.

**핵심 철학:**

> We do not generate a full video directly.  
> Instead, we decompose narrative into scene beats → generate scenes independently → re-compose using pacing constraints → apply style-consistent subtitle/cut rules.

숏폼은 "영상"이 아니라 **attention rhythm assembly**다.  
레퍼런스 영상의 스타일 핵심은 frame quality가 아니라 **cut sequencing**에 있다:

- 0~2초 hook
- reaction cut
- zoom timing
- subtitle burst
- emotional beat
- pacing transition

따라서 시스템의 목표는 "영상 생성"이 아니라 **영상 문법(Scene Grammar)을 생성하고 조립**하는 것이다.

**설계 원칙:**
- 전체 영상 one-shot 생성 금지 — 씬 단위 생성 후 조립
- Scene Grammar가 유일한 중간 표현 — 모든 스테이지가 이 JSON을 통해 소통
- Pacing Engine이 스타일을 결정 — 컷 길이·자막·전환이 deterministic
- 프롬프트는 코드에 박지 않는다 — 독립 파일로 분리, eval 가능
- Property를 1급 아티팩트로 관리 — 코드 변경 없이 확장
- 씬 단위 실패 복구 — scene 3 실패 시 scene 3만 재생성

---

## 1. 파이프라인 구조

### 1-1. 6단계 파이프라인

```
[입력] 텍스트 프롬프트
    ↓
┌─────────────────────┐
│  1. Story Parser    │  narrative → beat structure
│     (LLM)          │  emotional arc, hook position, climax point
└──────────┬──────────┘
           ↓ beat_structure.json
┌─────────────────────┐
│  2. Scene Planner   │  beat → scene_grammar.json
│     (LLM)          │  scene_type / duration / camera / emotion / pacing
└──────────┬──────────┘
           ↓ scene_grammar.json  ← 핵심 중간 표현
    ┌──────┴──────┐
    ↓             ↓
┌──────────┐  ┌──────────────────┐
│ 3. Scene │  │ 4. Subtitle      │
│ Generator│  │    Generator     │
│(Kling/   │  │ (ElevenLabs TTS  │
│ GPT-img) │  │  + Whisper align)│
└──────────┘  └──────────────────┘
    ↓ scene_assets/      ↓ subtitle_tracks/
    └──────┬─────────────┘
           ↓
┌─────────────────────┐
│  5. Pacing Engine   │  pacing_rules.json → timing manifest
│     (rule-based)    │  cut duration / transitions / zoom / bgm cues
└──────────┬──────────┘
           ↓ timing_manifest.json
┌─────────────────────┐
│  6. Video Composer  │  ffmpeg / Remotion → output.mp4
└──────────┬──────────┘
           ↓
      output.mp4 (9:16, 30~45초)
```

### 1-2. 시스템 레이어 구조

파이프라인 위에 3개 레이어가 얹힌다.

```
┌────────────────────────────────────────────────────────────┐
│  Layer 3: APO (Automatic Prompt Optimization)              │
│  출력 점수 → 후보 템플릿 생성 → eval → 승격                 │
└───────────────────────┬────────────────────────────────────┘
                        │ 피드백 루프
┌───────────────────────▼────────────────────────────────────┐
│  Layer 2: Template Staging System                          │
│  harness.yaml — 스테이지별 활성 템플릿 버전 결정            │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│  Layer 1: Prompt Template Library + Eval                   │
│  templates/{stage}/{version}.yaml — eval_cases 내장        │
└────────────────────────────────────────────────────────────┘
```

### 1-3. 완전 실행 흐름

```
[입력] 텍스트 프롬프트
    ↓ [L2] harness.yaml → active 템플릿 + active property 로드
    ↓ [L1] eval/runner.py → 사전 검증 (fail → 중단)
    ↓
    ↓ STAGE 1: Story Parser   → beat_structure.json
    ↓          consistency/checker.py (Pipeline Integrity)
    ↓
    ↓ STAGE 2: Scene Planner  → scene_grammar.json
    ↓          consistency/checker.py (ID + PC rules)
    ↓          consistency_anchors 확정 → assets/에 저장
    ↓
    ↓ STAGE 3: Scene Generator → scene_assets/ (병렬)
    ↓          씬별 생성 → Output Consistency 즉시 검증
    ↓          FAIL → 재생성 (max_retry: 2)
    ↓
    ↓ STAGE 4: Subtitle Generator → subtitle_tracks/
    ↓
    ↓ STAGE 5: Pacing Engine → timing_manifest.json
    ↓          consistency/checker.py (CS: scene_grammar × timing)
    ↓
    ↓ STAGE 6: Video Composer → output.mp4
    ↓          consistency_report.json 생성
    ↓
    ↓ [L3] scorer.py → rubric 점수화
    ↓ [L3] optimizer.py → 후보 템플릿 생성
    ↓ HITL Gate → 승인 시 harness.yaml 업데이트
```

---

## 2. 핵심 중간 표현 — Scene Grammar

Scene Grammar는 이 시스템의 **유일한 중간 계약**이다.  
모든 스테이지는 scene_grammar.json을 통해 소통한다.

```json
{
  "prompt": "사용자 입력 프롬프트 원문",
  "narrative": {
    "concept": "썸남 꼬시는 뷰티 루틴",
    "beat_count": 5,
    "total_duration_sec": 38,
    "target_persona": "girly",
    "emotional_arc": "curiosity → relatable → tip → excited → friendly"
  },
  "scenes": [
    {
      "id": 1,
      "scene_type": "hook",
      "duration": 2.0,
      "camera": "selfie-close",
      "subtitle_density": "high",
      "emotion": "curiosity",
      "voiceover": "썸남 100% 꼬시는 법 알려줄게",
      "visual_prompt": "20대 한국 여성, 정면 직캠, 자신감 있는 표정, 밝은 실내",
      "zoom": false,
      "transition_in": "cut",
      "transition_out": "cut",
      "bgm_cue": "fade_in"
    },
    {
      "id": 2,
      "scene_type": "reaction",
      "duration": 1.2,
      "camera": "medium-shot",
      "subtitle_density": "low",
      "emotion": "relatable",
      "voiceover": "솔직히 다들 고민이잖아",
      "visual_prompt": "같은 인물, 공감하는 표정, 약간 측면",
      "zoom": true,
      "transition_in": "cut",
      "transition_out": "smash-cut",
      "bgm_cue": "continue"
    },
    {
      "id": 3,
      "scene_type": "tip",
      "duration": 3.5,
      "camera": "medium-close",
      "subtitle_density": "medium",
      "emotion": "informative",
      "voiceover": "첫 번째는 향기야. 향이 기억에 남거든",
      "visual_prompt": "같은 인물, 손짓 포함, 설명하는 제스처",
      "zoom": false,
      "transition_in": "cut",
      "transition_out": "cut",
      "bgm_cue": "continue"
    },
    {
      "id": 4,
      "scene_type": "product_focus",
      "duration": 4.0,
      "camera": "product-closeup",
      "subtitle_density": "high",
      "caption_style": "burst",
      "emotion": "excited",
      "voiceover": "내가 요즘 꼭 챙겨다니는 거",
      "visual_prompt": "스너글 섬유탈취제 클로즈업, 손에 들고 있음",
      "zoom": false,
      "transition_in": "cut",
      "transition_out": "cut",
      "bgm_cue": "energy_up"
    },
    {
      "id": 5,
      "scene_type": "cta",
      "duration": 2.5,
      "camera": "selfie-medium",
      "subtitle_density": "medium",
      "emotion": "friendly",
      "voiceover": "올영세일 때 얼른 쟁여 girly❤️",
      "visual_prompt": "같은 인물, 손 흔들기, 웃는 표정",
      "zoom": false,
      "transition_in": "cut",
      "transition_out": "fade",
      "bgm_cue": "fade_out"
    }
  ],
  "consistency_anchors": {
    "character": {
      "reference_image": "assets/character_ref.png",
      "description": "20대 한국 여성, 갈색 웨이브 헤어, 베이지 니트 상의",
      "negative_prompt": "different hairstyle, different outfit, different person"
    },
    "background": {
      "style": "minimal_indoor_warm",
      "color_palette": ["#FAF0E6", "#D4A574", "#FFFFFF"]
    },
    "voice": {
      "tts_voice_id": "elevenlabs_kr_female_01",
      "speed_wpm": 180
    },
    "subtitle": {
      "font": "Noto Sans KR Bold",
      "color": "#FFFFFF",
      "stroke": "#000000",
      "position": "center",
      "emphasis_color": "#FF6B9D"
    }
  },
  "hashtags": ["#썸", "#뷰티팁", "#스킨케어"]
}
```

---

## 3. Pacing Engine

숏폼 스타일의 핵심. **컷 리듬이 스타일을 결정한다.**

### 3-1. pacing_rules.json

```json
{
  "hook_max_duration": 2.5,
  "avg_scene_length": 1.7,
  "caption_interval_ms": 900,
  "zoom_probability": 0.35,
  "smash_cut_probability": 0.25,
  "subtitle_burst_on_emphasis": true,
  "bgm_duck_ratio": 0.4,
  "energy_curve": "fast-open → slow-mid → fast-close",
  "scene_type_duration_bounds": {
    "hook":          { "min": 1.5, "max": 2.5 },
    "reaction":      { "min": 0.8, "max": 1.5 },
    "tip":           { "min": 2.0, "max": 5.0 },
    "product_focus": { "min": 3.0, "max": 6.0 },
    "cta":           { "min": 1.5, "max": 3.0 }
  },
  "transition_rules": {
    "hook → reaction":      "smash-cut",
    "reaction → tip":       "cut",
    "tip → product_focus":  "cut",
    "product_focus → cta":  "cut",
    "default":              "cut"
  }
}
```

pacing_rules.json은 style_profile에서 추출한 수치로 채워진다.

### 3-2. timing_manifest.json (Pacing Engine 출력)

```json
{
  "total_duration_sec": 38.0,
  "scenes": [
    {
      "id": 1,
      "start_sec": 0.0,
      "end_sec": 2.0,
      "transition_out": "cut",
      "zoom": false,
      "bgm": { "action": "fade_in", "volume": 0.3 },
      "subtitle_timing": [
        { "text": "썸남", "start_ms": 0, "end_ms": 400 },
        { "text": "100%", "start_ms": 400, "end_ms": 750, "emphasis": true },
        { "text": "꼬시는 법", "start_ms": 750, "end_ms": 1200 },
        { "text": "알려줄게", "start_ms": 1200, "end_ms": 2000 }
      ]
    }
  ],
  "bgm_track": "upbeat-kpop-inst",
  "bgm_duck_points": [
    { "start_sec": 0, "end_sec": 38, "ratio": 0.4 }
  ]
}
```

---

## 4. Property 시스템

스타일 property는 3단계 레이어로 관리된다.  
코드를 건드리지 않고 property 추가·변경·override가 가능하다.  
이 property들이 pacing_rules.json과 scene_grammar.json을 채운다.

### 4-1. Registry (전역 카탈로그)

```yaml
# properties/registry.yaml

properties:

  # ── 후크 ─────────────────────────────────────────────────
  hook.position_sec:
    type: number
    description: "후크 등장 시점 (초)"
    extract_method: whisper_timestamp
    maps_to: pacing_rules.hook_max_duration
    default_eval: { lte: 3.0 }
    apo_weight: high

  hook.type:
    type: enum
    values: [question, teaser, shock, list_preview, statement]
    extract_method: llm_classify
    maps_to: scene_grammar.scenes[0].scene_type_variant
    default_eval: required
    apo_weight: high

  # ── 컷 리듬 ──────────────────────────────────────────────
  cuts.avg_duration_sec:
    type: number
    extract_method: ffmpeg_scene_detect
    maps_to: pacing_rules.avg_scene_length
    default_eval: { gte: 1.0, lte: 5.0 }
    apo_weight: high

  cuts.rhythm_pattern:
    type: enum
    values: [fast-open, slow-open, constant, fast-close, accelerating]
    extract_method: llm_classify
    maps_to: pacing_rules.energy_curve
    apo_weight: high

  cuts.zoom_probability:
    type: number
    extract_method: visual_analysis
    maps_to: pacing_rules.zoom_probability
    default_eval: { gte: 0.0, lte: 1.0 }
    apo_weight: medium

  cuts.smash_cut_probability:
    type: number
    extract_method: visual_analysis
    maps_to: pacing_rules.smash_cut_probability
    apo_weight: medium

  # ── 자막 ─────────────────────────────────────────────────
  subtitle.sync_tightness:
    type: enum
    values: [tight, loose, none]
    extract_method: whisper_align
    maps_to: pacing_rules.caption_interval_ms
    apo_weight: medium

  subtitle.emphasis_style:
    type: enum
    values: [color_change, size_change, bold, underline, none]
    extract_method: vision_llm
    maps_to: scene_grammar.consistency_anchors.subtitle.emphasis_color
    apo_weight: low

  subtitle.position:
    type: enum
    values: [top, center, bottom, dynamic]
    extract_method: vision_llm
    maps_to: scene_grammar.consistency_anchors.subtitle.position
    apo_weight: low

  subtitle.burst_on_emphasis:
    type: boolean
    extract_method: llm_classify
    maps_to: pacing_rules.subtitle_burst_on_emphasis
    apo_weight: medium

  # ── 오디오 / BGM ─────────────────────────────────────────
  bgm.entry_sec:
    type: number
    extract_method: audio_analysis
    apo_weight: low

  bgm.duck_ratio:
    type: number
    extract_method: audio_analysis
    maps_to: pacing_rules.bgm_duck_ratio
    apo_weight: low

  bgm.genre:
    type: string
    extract_method: llm_classify
    apo_weight: low

  # ── 내러티브 ─────────────────────────────────────────────
  narrative.target_persona:
    type: string
    description: "타겟 직접 호칭 (girly, 언니들 등)"
    extract_method: llm_extract
    maps_to: scene_grammar.narrative.target_persona
    apo_weight: high

  narrative.ppl_present:
    type: boolean
    extract_method: llm_classify
    maps_to: scene_grammar.scenes[].scene_type (product_focus 포함 여부)
    apo_weight: medium

  narrative.ppl_bridge_phrase:
    type: string
    extract_method: llm_extract
    apo_weight: medium

  narrative.segment_ratio:
    type: object
    description: "hook/reaction/tip/product_focus/cta 비율"
    extract_method: llm_segment
    maps_to: scene_grammar.scenes[].duration 배분
    apo_weight: medium

  narrative.emotional_arc:
    type: string
    description: "씬 간 감정 흐름"
    extract_method: llm_classify
    maps_to: scene_grammar.narrative.emotional_arc
    apo_weight: medium

  # ── 확장 슬롯 ────────────────────────────────────────────
  custom.*:
    type: any
    extract_method: user_defined
    apo_weight: user_defined
```

**`maps_to` 필드**: 각 property가 어느 중간 산출물의 어느 필드를 채우는지 명시.  
property 추가 시 코드 없이 이 한 줄로 파이프라인 반영 경로가 결정된다.

### 4-2. Preset (장르별 묶음)

```yaml
# properties/presets/lifestyle_kr.yaml
name: "한국 라이프스타일 숏폼"

active_properties:
  - hook.position_sec
  - hook.type
  - cuts.avg_duration_sec
  - cuts.rhythm_pattern
  - cuts.zoom_probability
  - cuts.smash_cut_probability
  - subtitle.sync_tightness
  - subtitle.emphasis_style
  - subtitle.burst_on_emphasis
  - bgm.entry_sec
  - bgm.duck_ratio
  - narrative.target_persona
  - narrative.ppl_present
  - narrative.ppl_bridge_phrase
  - narrative.segment_ratio
  - narrative.emotional_arc

weights:
  hook.position_sec:            0.15
  hook.type:                    0.10
  cuts.avg_duration_sec:        0.15
  cuts.rhythm_pattern:          0.10
  cuts.zoom_probability:        0.05
  subtitle.sync_tightness:      0.10
  subtitle.burst_on_emphasis:   0.05
  narrative.target_persona:     0.12
  narrative.emotional_arc:      0.08
  narrative.segment_ratio:      0.10
```

### 4-3. Custom (레퍼런스별 override)

```yaml
# properties/custom/amyglamy.yaml
name: "AmyGlamy 스타일"
extends: presets/lifestyle_kr.yaml

add_properties:
  - narrative.direct_address_style

overrides:
  hook.position_sec:
    eval: { lte: 2.5 }
  cuts.avg_duration_sec:
    eval: { gte: 1.0, lte: 3.0 }
  cuts.zoom_probability:
    eval: { gte: 0.3 }

custom_properties:
  narrative.direct_address_style:
    type: string
    description: "girly / 언니 / 자기야 등 페르소나 호칭 패턴"
    extract_method: llm_extract
    maps_to: scene_grammar.narrative.target_persona
    apo_weight: high
```

---

## 5. Layer 1 — Prompt Template Library

각 스테이지별 템플릿은 독립 파일로 분리, eval_cases 내장.

### 5-1. 템플릿 포맷 (Story Parser)

```yaml
# templates/story_parser/v1.yaml
id: story-parser-v1
stage: story_parser
version: "1.0"
description: "사용자 프롬프트 → beat structure 추출"

input:
  user_prompt: { type: string }
  target_persona: { type: string }
  total_duration_sec: { type: number }
  emotional_arc_pattern: { type: string, description: "style_profile에서 추출" }

output:
  schema: "schemas/beat_structure.schema.json"
  format: json

system: |
  You are a shortform video narrative designer specialized in Korean lifestyle content.
  Decompose the user's concept into emotional beats that drive attention.
  Each beat must have a clear emotional function and contribute to the pacing arc.

user: |
  Create a beat structure for this shortform video concept.

  ## User Concept
  {{ user_prompt }}

  ## Target Persona
  {{ target_persona }}

  ## Total Duration
  {{ total_duration_sec }}s

  ## Emotional Arc Pattern
  {{ emotional_arc_pattern }}

  Extract beats following this arc. Each beat needs:
  - emotional function (hook / empathy / tip / reveal / cta)
  - duration ratio
  - energy level (low / medium / high)

eval_cases:
  - id: "story_parser_case_001"
    input_fixture: "eval/fixtures/story_parser/case_001.json"
    expected:
      "beats[0].function": "hook"
      "beats[0].energy": "high"
      "beats[-1].function": "cta"
```

### 5-2. 템플릿 포맷 (Scene Planner)

```yaml
# templates/scene_planner/v1.yaml
id: scene-planner-v1
stage: scene_planner
version: "1.0"
description: "beat structure → scene_grammar.json 생성"

input:
  beat_structure: { type: object }
  style_profile: { type: object }
  pacing_rules: { type: object }
  active_properties: { type: object }

output:
  schema: "schemas/scene_grammar.schema.json"
  format: json

system: |
  You are a shortform video scene director.
  Convert narrative beats into concrete scene grammar.
  Each scene must have precise camera, emotion, subtitle density, and visual direction.
  The output is deterministic assembly instructions — not creative writing.

user: |
  Generate scene grammar from these beats.

  ## Beat Structure
  {{ beat_structure }}

  ## Style Constraints (must reproduce)
  - hook.position_sec ≤ {{ style_profile.hook.position_sec }}s
  - avg_scene_length ≈ {{ pacing_rules.avg_scene_length }}s
  - zoom_probability = {{ pacing_rules.zoom_probability }}
  - target_persona address: {{ style_profile.narrative.target_persona }}

  ## Active Scene Types
  {{ active_properties.narrative.segment_ratio }}

  Return scene_grammar JSON. Scenes must be self-contained generation units.

eval_cases:
  - id: "scene_planner_case_001"
    input_fixture: "eval/fixtures/scene_planner/case_001.json"
    expected:
      "scenes[0].scene_type": "hook"
      "scenes[0].duration": { lte: 2.5 }
      "narrative.emotional_arc": { contains: "curiosity" }
```

### 5-3. 템플릿 포맷 (Scene Generator)

```yaml
# templates/scene_generator/v1.yaml
id: scene-generator-v1
stage: scene_generator
version: "1.0"
description: "씬 1개 → 비주얼 생성 프롬프트 + API 파라미터"

input:
  scene: { type: object, description: "scene_grammar.scenes[i]" }
  consistency_anchors: { type: object }
  generation_backend: { type: enum, values: [kling, gpt_image_2, runway] }

output:
  schema: "schemas/generation_request.schema.json"
  format: json

system: |
  You are a visual prompt engineer for Korean shortform video.
  Convert scene grammar into a precise generation request for the target backend.
  Consistency anchors must be embedded in every prompt.

user: |
  Generate a visual creation request for this scene.

  ## Scene
  {{ scene }}

  ## Consistency Anchors (must be reproduced)
  Character: {{ consistency_anchors.character.description }}
  Background: {{ consistency_anchors.background.style }}
  Negative: {{ consistency_anchors.character.negative_prompt }}

  ## Backend
  {{ generation_backend }}

  Return a generation_request JSON with backend-specific parameters.
```

---

## 6. Layer 2 — Template Staging System

### 6-1. harness.yaml

```yaml
# harness.yaml
version: "0.3"

# Property 설정
properties:
  preset: properties/presets/lifestyle_kr.yaml
  custom: properties/custom/amyglamy.yaml

# 스테이지별 템플릿 버전
stages:
  story_parser:
    active: v1
    candidates:
      v1: templates/story_parser/v1.yaml

  scene_planner:
    active: v1
    candidates:
      v1: templates/scene_planner/v1.yaml
      v2: templates/scene_planner/v2.yaml    # 개발중

  scene_generator:
    active: v1
    candidates:
      v1: templates/scene_generator/v1.yaml

  subtitle_generator:
    active: v1
    candidates:
      v1: templates/subtitle_generator/v1.yaml

  pacing_engine:
    backend: rule_based                       # LLM 아님, pacing_rules.json 직접 적용

  video_composer:
    backend: ffmpeg                           # or remotion
    output_format: mp4
    resolution: "1080x1920"                  # 9:16

# Eval
eval:
  auto_run: true
  fail_on_schema_error: true

# APO
apo:
  enabled: true
  min_score_delta: 0.15
  hitl_required: true

# 생성 백엔드
generation:
  visual: kling                              # kling | gpt_image_2 | runway
  tts: elevenlabs
  tts_voice_id: elevenlabs_kr_female_01
```

---

## 7. Layer 3 — APO

### 7-1. 루브릭

```yaml
# feedback/rubric.yaml
dimensions:
  hook:
    weight: 0.25
    criteria:
      within_2_5s:      { type: binary }
      question_format:  { type: binary }
      target_address:   { type: binary }

  cut_rhythm:
    weight: 0.25
    criteria:
      avg_cut_matches:  { type: range, target: 1.7, tolerance: 0.4 }
      energy_curve:     { type: scale, range: [0, 10] }
      zoom_applied:     { type: binary }

  subtitle:
    weight: 0.20
    criteria:
      speech_sync:      { type: scale, range: [0, 10] }
      burst_on_emphasis:{ type: binary }

  ppl_integration:
    weight: 0.15
    criteria:
      natural_bridge:   { type: scale, range: [0, 10] }

  human:
    weight: 0.15
    criteria:
      overall_match:    { type: scale, range: [0, 10] }
```

### 7-2. APO 루프

```
[1] active 템플릿 실행 → 출력 수집
[2] scorer.py → rubric weighted_score 계산
[3] optimizer.py → meta-prompt로 후보 템플릿 생성
    (낮은 dimension 집중: "cut_rhythm 점수가 낮다. avg_scene_length 제약 강화하라")
[4] eval/runner.py → fixture 기준 후보 검증
[5] HITL Gate → 승인 시 버전 승격 + runs.jsonl 기록
```

---

## 8. 검증 시스템

### 8-1. 검증 레이어 요약

| 시스템 | 질문 | 실행 시점 |
|--------|------|----------|
| `schemas/` | JSON 형식이 맞는가? | 각 스테이지 출력 직후 |
| `eval/runner.py` | 템플릿이 fixture 기준 출력을 내는가? | 파이프라인 진입 전 |
| `consistency/checker.py` | Scene Grammar와 Pacing이 서로 맞는가? | Stage 2·5 직후 |
| `consistency/checker.py` | 생성된 씬 자산이 property별로 일관된가? | Stage 3 씬별 즉시 |
| `apo/scorer.py` | 영상이 레퍼런스 스타일에 얼마나 가까운가? | 영상 완성 후 |

### 8-2. Output Consistency — Property별 정의

```yaml
# consistency/properties.yaml

properties:

  character.visual:
    description: "캐릭터 얼굴·의상·헤어가 씬 전체에서 동일"
    applies_to: scene_assets
    measurement:
      method: image_embedding_similarity
      model: CLIP
      compare: each_scene_vs_anchor
      threshold: 0.85
    on_fail: flag_regenerate
    severity: error
    apo_weight: high

  background.style:
    description: "배경 장소·조명·색감이 씬 전체에서 일관"
    applies_to: scene_assets
    measurement:
      method: image_embedding_similarity
      model: CLIP
      compare: each_scene_vs_anchor
      threshold: 0.70
    on_fail: flag_regenerate
    severity: warning
    apo_weight: medium

  voice.identity:
    description: "동일 TTS 보이스 ID가 전체 씬에 사용됨"
    applies_to: scene_audio
    measurement:
      method: voice_id_exact_match
    on_fail: error
    severity: error
    apo_weight: high

  voice.energy_level:
    description: "씬 간 에너지 레벨 급변 없음 (RMS 기준)"
    applies_to: scene_audio
    measurement:
      method: audio_rms_variance
      max_variance: 0.15
    on_fail: warn
    severity: warning
    apo_weight: medium

  subtitle.style:
    description: "자막 폰트·색상·위치·강조 방식이 씬 전체에서 동일"
    applies_to: scene_subtitle_configs
    measurement:
      method: config_exact_match
      keys: [font, color, position, emphasis_style]
    on_fail: error
    severity: error
    apo_weight: medium

  pacing.rhythm:
    description: "컷 길이 분포가 pacing_rules 기준에서 벗어나지 않음"
    applies_to: scene_durations
    measurement:
      method: duration_stddev_ratio
      max_stddev_ratio: 0.30
    on_fail: warn
    severity: warning
    apo_weight: medium
```

### 8-3. Pipeline Integrity Rules

```yaml
# consistency/rules/pipeline_integrity.yaml
rules:
  - id: PI001  # beat_structure.total_sec == Σ beat durations
  - id: PI002  # scene_grammar.scenes[0].scene_type == "hook"
  - id: PI003  # ppl_present → scenes에 product_focus 존재
  - id: PI004  # timing_manifest scene 수 == scene_grammar scene 수
  - id: PI005  # all active_properties keys in style_profile
  - id: PI006  # pacing_rules.avg_scene_length ≈ mean(scene durations) ±20%
```

---

## 9. 기술 스택

| 도구 | 스테이지 | 선택 이유 |
|------|---------|----------|
| `yt-dlp` | 레퍼런스 다운로드 | 무료, 안정적 |
| `ffmpeg` | Scene 분할·오디오 추출·최종 합성 | 업계 표준, deterministic |
| `Remotion` | Video Composer (대안) | React 기반, 자막·애니메이션 정밀 제어 |
| `openai-whisper` | STT + 타임스탬프 | 한국어 정확도, 오픈소스 |
| `Claude API` | Story Parser · Scene Planner · APO | JSON mode, 한국어 품질 |
| `GPT Image 2` | Scene Generator (이미지) | 9:16 지원, 한국어 텍스트 렌더링, 공식 API |
| `Kling AI` | Scene Generator (영상) | Character Reference 내장, API 제공 |
| `ElevenLabs` | TTS (한국어) | 자연스러운 억양, REST API |
| `CLIP` | Consistency 검증 | 이미지 임베딩 유사도 |

**왜 Kling/GPT Image 2 조합인가:**
- GPT Image 2: 씬 이미지 생성, 한국어 텍스트 포함, 9:16 직접 지정
- Kling AI: 이미지 → 영상 애니메이션, Character Reference로 일관성 유지
- Midjourney: API 없음 → 파이프라인 불가

---

## 10. 디렉토리 구조

```
shortform-harness/
│
├── harness.yaml                         ← [L2] 스테이징 설정
│
├── properties/                          ← Property 시스템
│   ├── registry.yaml
│   ├── presets/lifestyle_kr.yaml
│   └── custom/amyglamy.yaml
│
├── templates/                           ← [L1] Prompt Template Library
│   ├── story_parser/v1.yaml
│   ├── scene_planner/v1.yaml
│   ├── scene_generator/v1.yaml
│   └── subtitle_generator/v1.yaml
│
├── schemas/                             ← JSON 스키마 (eval 기준)
│   ├── beat_structure.schema.json
│   ├── scene_grammar.schema.json        ← 핵심 중간 표현 스키마
│   ├── generation_request.schema.json
│   └── timing_manifest.schema.json
│
├── eval/                                ← [L1] Template Eval
│   ├── runner.py
│   └── fixtures/
│       ├── story_parser/case_001.json
│       ├── scene_planner/case_001.json
│       └── scene_generator/case_001.json
│
├── feedback/rubric.yaml                 ← [L3] APO 루브릭
│
├── apo/                                 ← [L3] Optimization Engine
│   ├── scorer.py
│   ├── optimizer.py
│   ├── candidates/
│   └── history/runs.jsonl
│
├── consistency/                         ← Validation
│   ├── checker.py
│   ├── properties.yaml                  ← Output Consistency (property별)
│   └── rules/pipeline_integrity.yaml   ← Pipeline Integrity
│
├── pipeline/                            ← [L2] 실행 레이어
│   ├── loader.py
│   ├── story_parser.py
│   ├── scene_planner.py
│   ├── scene_generator.py              ← 씬별 병렬 실행
│   ├── subtitle_generator.py
│   ├── pacing_engine.py               ← rule-based, LLM 아님
│   └── video_composer.py              ← ffmpeg / Remotion
│
├── data/                               ← 런타임 산출물
│   ├── style_profile.json
│   ├── beat_structure.json
│   ├── scene_grammar.json              ← 핵심 중간 표현
│   ├── pacing_rules.json
│   └── timing_manifest.json
│
├── assets/                             ← 생성된 씬 자산
│   ├── character_ref.png
│   ├── scene_001.mp4
│   ├── scene_002.mp4
│   └── subtitles/scene_001.srt
│
├── outputs/
│   ├── video_01.mp4
│   ├── video_02.mp4
│   └── prompts.md
│
└── run.sh
```

---

## 11. 구현 우선순위 (Cut-line)

| 우선순위 | 유지 | 포기 가능 |
|---------|------|----------|
| P0 | `scene_grammar.schema.json` 스키마 정의 | — |
| P0 | `templates/scene_planner/v1.yaml` + eval fixture | v2 이상 |
| P0 | `pacing_rules.json` + `pacing_engine.py` | Remotion (ffmpeg로 대체) |
| P1 | `properties/registry.yaml` + `custom/amyglamy.yaml` | — |
| P1 | `pipeline/scene_generator.py` (Kling or GPT Image 2) | 고화질 |
| P2 | 영상 2편 (동일 시스템, 다른 프롬프트) | 영상 품질 |
| P3 | `apo/scorer.py` + `consistency/checker.py` | `apo/optimizer.py` |

---

## 12. 제출물 체크리스트

```
□ README.md        — 실행 방법 + "We do not generate full video" 아키텍처 설명
□ analysis.md      — 레퍼런스 분석 (cut rhythm, pacing 수치 포함)
□ retro.md         — 가설, 막힌 지점, 개선점
□ harness.yaml
□ templates/       — 4 스테이지 × v1
□ properties/      — registry + preset + custom
□ schemas/         — 4개 스키마
□ eval/            — runner + fixtures
□ data/*.json      — 중간 산출물 (scene_grammar.json 필수)
□ outputs/*.mp4    — 생성 영상 2편 이상
□ outputs/prompts.md
```
