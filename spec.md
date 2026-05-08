# Shortform Video Generation Harness — System Spec

> version: 0.2.0  
> status: draft  
> date: 2026-05-08

---

## 0. Overview

텍스트 프롬프트 하나를 받아 레퍼런스 숏폼 영상의 스타일을 따르는 숏폼 영상을 생성하는 재사용 가능한 파이프라인.

**핵심 설계 원칙:**
- "영상 1편"이 아니라 "같은 시스템으로 다른 입력 → 다른 결과"를 증명하는 시스템
- 프롬프트는 코드에 박지 않는다 — 독립 파일로 분리, eval 가능
- 분석↔생성 단계를 JSON 계약으로 완전 분리
- Property를 1급 아티팩트로 관리 — 코드 변경 없이 확장

---

## 1. 시스템 레이어 구조

시스템은 3개 레이어로 구성된다.

```
┌────────────────────────────────────────────────────────────┐
│  Layer 3: APO (Automatic Prompt Optimization)              │
│  피드백 루프 — 출력 점수 → 후보 템플릿 생성 → eval → 승격   │
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

### 실행 흐름 요약

```
[입력] 텍스트 프롬프트
    ↓ [L2] harness.yaml → active 템플릿 + active property 로드
    ↓ [L1] eval/runner.py → 활성 템플릿 사전 검증 (fail → 중단)
    ↓
    ↓ [L1] STAGE 1: analyze   → style_profile.json
    ↓       consistency/checker.py (Intra-doc: ID rules)
    ↓       consistency/checker.py (Property-contract: PC rules)
    ↓
    ↓ [L1] STAGE 2: script    → scene_script.json
    ↓       consistency/checker.py (Intra-doc: ID rules)
    ↓       consistency/checker.py (Cross-stage: CS rules — style_profile × scene_script)
    ↓
    ↓ [L1] STAGE 3: assemble  → assemble_plan.json → output.mp4
    ↓       consistency/checker.py (Cross-stage: CS rules — scene_script × assemble_plan)
    ↓
    ↓ [L3] scorer.py          → rubric 점수화
    ↓ [L3] optimizer.py       → 후보 템플릿 생성
    ↓       consistency/checker.py (전체 cross-stage: 후보 템플릿 회귀 검증)
    ↓ HITL Gate               → 승인 시 harness.yaml 업데이트
```

---

## 2. Property 시스템

스타일 property는 3단계 레이어로 관리된다.
코드를 건드리지 않고 property 추가·변경·override가 가능하다.

### 2-1. Registry (전역 카탈로그)

```yaml
# properties/registry.yaml

properties:

  # ── 시간 구조 ────────────────────────────────────────────
  hook.position_sec:
    type: number
    description: "후크 등장 시점 (초)"
    extract_method: whisper_timestamp
    default_eval: { lte: 3.0 }
    apo_weight: high

  hook.type:
    type: enum
    values: [question, teaser, shock, list_preview, statement]
    extract_method: llm_classify
    default_eval: required
    apo_weight: high

  cuts.avg_duration_sec:
    type: number
    extract_method: ffmpeg_scene_detect
    default_eval: { gte: 1.0, lte: 5.0 }
    apo_weight: medium

  cuts.rhythm_pattern:
    type: enum
    values: [fast-open, slow-open, constant, fast-close, accelerating]
    extract_method: llm_classify
    apo_weight: medium

  # ── 자막 ─────────────────────────────────────────────────
  subtitle.sync_tightness:
    type: enum
    values: [tight, loose, none]
    extract_method: whisper_align
    apo_weight: medium

  subtitle.emphasis_style:
    type: enum
    values: [color_change, size_change, bold, underline, none]
    extract_method: vision_llm
    apo_weight: low

  subtitle.position:
    type: enum
    values: [top, center, bottom, dynamic]
    extract_method: vision_llm
    apo_weight: low

  # ── 오디오 / BGM ─────────────────────────────────────────
  bgm.entry_sec:
    type: number
    extract_method: audio_analysis
    apo_weight: low

  bgm.duck_on_speech:
    type: boolean
    extract_method: audio_analysis
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
    apo_weight: high

  narrative.ppl_present:
    type: boolean
    extract_method: llm_classify
    apo_weight: medium

  narrative.ppl_bridge_phrase:
    type: string
    description: "PPL 자연 연결 구문 패턴"
    extract_method: llm_extract
    apo_weight: medium

  narrative.segment_ratio:
    type: object
    description: "hook/empathy/tip/ppl/cta 비율 (합산 1.0)"
    extract_method: llm_segment
    apo_weight: medium

  # ── 확장 슬롯 ────────────────────────────────────────────
  custom.*:
    type: any
    extract_method: user_defined
    apo_weight: user_defined
```

### 2-2. Preset (장르별 묶음)

```yaml
# properties/presets/lifestyle_kr.yaml
name: "한국 라이프스타일 숏폼"

active_properties:
  - hook.position_sec
  - hook.type
  - cuts.avg_duration_sec
  - cuts.rhythm_pattern
  - subtitle.sync_tightness
  - subtitle.emphasis_style
  - bgm.entry_sec
  - bgm.duck_on_speech
  - narrative.target_persona
  - narrative.ppl_present
  - narrative.ppl_bridge_phrase
  - narrative.segment_ratio

weights:
  hook.position_sec:           0.20
  hook.type:                   0.15
  cuts.avg_duration_sec:       0.15
  narrative.target_persona:    0.12
  narrative.ppl_bridge_phrase: 0.10
  subtitle.sync_tightness:     0.10
  cuts.rhythm_pattern:         0.08
  narrative.segment_ratio:     0.10
```

### 2-3. Custom (레퍼런스별 override)

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

custom_properties:
  narrative.direct_address_style:
    type: string
    description: "girly / 언니 / 자기야 등 페르소나 호칭 패턴"
    extract_method: llm_extract
    apo_weight: high
```

### 2-4. Property 작업별 변경 파일

| 작업 | 변경 파일 | 코드 변경 |
|------|----------|----------|
| 신규 property 정의 | `registry.yaml` | 없음 |
| 레퍼런스별 추가/override | `custom/{채널}.yaml` | 없음 |
| 장르 기본값 변경 | `presets/{장르}.yaml` | 없음 |
| extract_method 구현 추가 | `pipeline/extractors.py` | 있음 |

---

## 3. Layer 1 — Prompt Template Library

### 3-1. 템플릿 포맷

```yaml
# templates/analyze/v1.yaml
id: analyze-style-v1
stage: analyze
version: "1.0"
description: "레퍼런스 영상에서 스타일 프로파일 추출"

input:
  transcript:
    type: string
    description: "Whisper 타임스탬프 포함 스크립트"
  cut_durations:
    type: array
    description: "ffmpeg 장면 분할 결과 (초 단위)"
  video_duration:
    type: number
  active_properties:
    type: object
    description: "loader.py가 주입 — registry + custom 조합 결과"

output:
  schema: "schemas/style_profile.schema.json"
  format: json

system: |
  You are an expert at analyzing Korean short-form video style.
  Extract precise, measurable parameters from the given transcript and cut data.
  Return valid JSON matching the output schema exactly.
  Only include keys listed in active_properties.

user: |
  Analyze this YouTube Short and extract the style profile.

  ## Properties to Extract
  {{ active_properties }}

  ## Transcript (with timestamps)
  {{ transcript }}

  ## Cut Durations (seconds)
  {{ cut_durations }}

  ## Video Total Duration
  {{ video_duration }}s

  Return a JSON object with exactly the property keys listed above.

# eval 케이스 — 템플릿에 내장
eval_cases:
  - id: "amyglamy_case_001"
    input_fixture: "eval/fixtures/analyze/amyglamy_001.json"
    expected:
      "hook.type": "question"
      "hook.position_sec": { lte: 2.5 }
      "cuts.avg_duration_sec": { gte: 1.0, lte: 3.0 }
      "subtitle.sync_tightness": "tight"
```

```yaml
# templates/script/v1.yaml
id: script-gen-v1
stage: script
version: "1.0"
description: "style_profile + 프롬프트 → scene_script 생성"

input:
  user_prompt:
    type: string
    description: "영상 스토리·컨셉 (자유 형식)"
  style_profile:
    type: object
    description: "analyze 스테이지 출력"
  active_properties:
    type: object

output:
  schema: "schemas/scene_script.schema.json"
  format: json

system: |
  You are a Korean short-form video scriptwriter.
  Generate a scene-by-scene script that matches the given style profile exactly.
  Every measurable parameter in the style profile must be reflected in the script.

user: |
  Create a short-form video script based on:

  ## User Concept
  {{ user_prompt }}

  ## Style Profile (must be reproduced)
  {{ style_profile }}

  ## Output Schema
  {{ output_schema }}

  Ensure:
  - Hook appears within {{ style_profile.hook.position_sec }}s
  - Hook type is {{ style_profile.hook.type }}
  - Average cut duration ≈ {{ style_profile.cuts.avg_duration_sec }}s
  - Target persona addressed as: {{ style_profile.narrative.target_persona }}

eval_cases:
  - id: "script_case_001"
    input_fixture: "eval/fixtures/script/case_001.json"
    expected:
      "scenes[0].segment": "hook"
      "scenes[0].duration_sec": { lte: 2.5 }
      "total_duration_sec": { gte: 30, lte: 45 }
```

```yaml
# templates/assemble/v1.yaml
id: assemble-v1
stage: assemble
version: "1.0"
description: "scene_script → 조립 지시 생성 (TTS 파라미터, 자막 스타일, BGM 큐)"

input:
  scene_script:
    type: object
  style_profile:
    type: object

output:
  schema: "schemas/assemble_plan.schema.json"
  format: json

system: |
  You are a video post-production specialist.
  Convert the scene script into precise technical assembly instructions.

user: |
  Generate assembly instructions for this scene script.

  ## Scene Script
  {{ scene_script }}

  ## Style Reference
  - Subtitle style: {{ style_profile.subtitle.emphasis_style }}
  - Subtitle position: {{ style_profile.subtitle.position }}
  - BGM entry: {{ style_profile.bgm.entry_sec }}s
  - Speech duck: {{ style_profile.bgm.duck_on_speech }}

  Return assembly_plan JSON.

eval_cases:
  - id: "assemble_case_001"
    input_fixture: "eval/fixtures/assemble/case_001.json"
    expected:
      "scenes[0].tts.language": "ko"
      "bgm.entry_sec": { lte: 1.0 }
```

---

## 4. Layer 2 — Template Staging System

### 4-1. harness.yaml

```yaml
# harness.yaml
version: "0.1"

# Property 설정
properties:
  preset: properties/presets/lifestyle_kr.yaml
  custom: properties/custom/amyglamy.yaml     # 없으면 preset만 사용

# 스테이지별 템플릿 버전 관리
stages:
  analyze:
    active: v1
    candidates:
      v1: templates/analyze/v1.yaml
      v2: templates/analyze/v2.yaml           # 개발중

  script:
    active: v1
    candidates:
      v1: templates/script/v1.yaml
      v2: templates/script/v2.yaml            # PPL 브리지 강화

  assemble:
    active: v1
    candidates:
      v1: templates/assemble/v1.yaml

# Eval 설정
eval:
  auto_run: true                              # 파이프라인 실행 전 자동 검증
  fail_on_schema_error: true                  # FAIL 시 파이프라인 진입 차단

# APO 설정
apo:
  enabled: true
  min_score_delta: 0.15                       # 15% 이상 개선 시 자동 승격 후보
  hitl_required: true                         # 최종 승격은 인간 승인 필수
```

### 4-2. loader.py 책임

```
1. harness.yaml 파싱
2. properties.preset 로드 → active_properties 목록 확정
3. properties.custom 존재 시 → override / add_properties 적용
4. registry.yaml에서 각 property 메타데이터 조회
5. 각 stage의 active 템플릿 파일 로드
6. 템플릿 변수 {{ active_properties }} 렌더링
7. eval.auto_run: true → eval/runner.py 선실행, FAIL 시 중단
```

---

## 5. Layer 3 — APO (Automatic Prompt Optimization)

### 5-1. 루브릭

```yaml
# feedback/rubric.yaml
dimensions:
  hook:
    weight: 0.30
    criteria:
      within_3s:        { type: binary }
      question_format:  { type: binary }
      target_address:   { type: binary }

  pacing:
    weight: 0.25
    criteria:
      avg_cut_sec:      { type: range, target: 2.3, tolerance: 0.5 }
      hook_cut_shorter: { type: binary }

  subtitle:
    weight: 0.20
    criteria:
      speech_sync:      { type: scale, range: [0, 10] }
      emphasis_present: { type: binary }

  ppl_integration:
    weight: 0.15
    criteria:
      natural_bridge:   { type: scale, range: [0, 10] }
      position:         { type: enum, values: [mid, end] }

  human:
    weight: 0.10
    criteria:
      overall_match:    { type: scale, range: [0, 10] }
```

### 5-2. APO 루프

```
[1] 현재 active 템플릿 실행 → 출력 수집
      ↓
[2] scorer.py
    루브릭 각 dimension 점수 계산
    weighted_score = Σ(dimension_score × weight)
      ↓
[3] optimizer.py
    meta-prompt → Claude API:
    "이 템플릿은 pacing 점수 5/10이다.
     cut_duration 제약 조건을 더 명시적으로 지정하여 개선하라.
     변경된 템플릿 YAML을 반환하라."
    → N개 후보 생성 → apo/candidates/ 저장
      ↓
[4] eval/runner.py
    후보 vs 현재 fixture 점수 비교
    delta = candidate_score - current_score
      ↓
[5] HITL Gate
    자동 승격 조건:  delta >= min_score_delta AND schema 100% pass
    인간 승인 조건:  delta > 0 AND human dimension 포함 시
      ↓
[6] 승인 시
    templates/{stage}/v{n+1}.yaml 확정
    harness.yaml active 업데이트
    apo/history/runs.jsonl 기록
```

### 5-3. runs.jsonl 포맷

```jsonl
{
  "run_id": "r001",
  "stage": "analyze",
  "from_version": "v1",
  "to_version": "v1.1",
  "score_delta": { "pacing": +2.1, "hook": 0.0, "total": +1.4 },
  "promoted": true,
  "promoted_by": "human",
  "timestamp": "2026-05-08T14:22:00Z"
}
{
  "run_id": "r002",
  "stage": "script",
  "from_version": "v1",
  "to_version": "v1.1-cand",
  "score_delta": { "ppl_integration": +1.3, "total": +0.8 },
  "promoted": false,
  "rejection_reason": "human_rejected: PPL 너무 강요됨",
  "timestamp": "2026-05-08T16:05:00Z"
}
```

---

## 6. 검증 시스템 (Validation System)

4개 레이어가 각각 다른 질문에 답한다.

| 시스템 | 질문 | 기준 | 실행 시점 |
|--------|------|------|----------|
| `schemas/` | JSON 형식이 맞는가? | 타입·구조 | 각 스테이지 출력 직후 |
| `eval/runner.py` | 이 템플릿이 fixture 입력에 대해 기대 출력을 내는가? | fixture 고정값 | 파이프라인 진입 전 |
| `consistency/checker.py` | **생성된 결과물이 property별로 영상 전체에서 일관된가?** | property 정의 | Stage 3 씬 생성 중·후 |
| `apo/scorer.py` | 생성된 영상이 레퍼런스 스타일에 얼마나 가까운가? | 루브릭 점수 | 영상 완성 후 |

---

### 6-1. Output Consistency — Property별 정의

일관성 검증은 **property 단위로 정의**된다.  
각 property는 씬 간 비교 방식(method)과 허용 임계값(threshold)을 갖는다.

```yaml
# consistency/properties.yaml

properties:

  # ── 비주얼 ────────────────────────────────────────────────

  character.visual:
    description: "캐릭터 얼굴·의상·헤어가 씬 전체에서 동일"
    applies_to: scene_assets           # 생성된 이미지/영상 프레임
    measurement:
      method: image_embedding_similarity
      model: CLIP
      compare: each_scene_vs_anchor    # 첫 씬을 앵커로 나머지와 비교
      threshold: 0.85
    on_fail: flag_regenerate           # 해당 씬 재생성 트리거
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

  color_palette:
    description: "전체 영상의 주요 색감 분포가 씬 간 유사"
    applies_to: scene_assets
    measurement:
      method: histogram_similarity
      bins: 16
      threshold: 0.75
    on_fail: warn
    severity: warning
    apo_weight: low

  # ── 오디오 ────────────────────────────────────────────────

  voice.identity:
    description: "동일 TTS 보이스 ID가 전체 씬에 사용됨"
    applies_to: scene_audio
    measurement:
      method: voice_id_exact_match     # assemble_plan의 voice_id 키 일치
      compare: all_scenes_same
    on_fail: error
    severity: error
    apo_weight: high

  voice.energy_level:
    description: "씬 간 에너지 레벨 급변 없음"
    applies_to: scene_audio
    measurement:
      method: audio_rms_variance
      max_variance: 0.15               # RMS 기준 ±15% 이내
    on_fail: warn
    severity: warning
    apo_weight: medium

  voice.speaking_rate:
    description: "발화 속도(WPM)가 씬 간 일관"
    applies_to: scene_audio
    measurement:
      method: wpm_variance
      max_variance: 0.20
    on_fail: warn
    severity: warning
    apo_weight: low

  # ── 자막 ─────────────────────────────────────────────────

  subtitle.style:
    description: "자막 폰트·색상·위치·강조 방식이 씬 전체에서 동일"
    applies_to: scene_subtitle_configs
    measurement:
      method: config_exact_match       # assemble_plan의 subtitle 설정 키 비교
      keys: [font, color, position, emphasis_style]
    on_fail: error
    severity: error
    apo_weight: medium

  # ── 타이밍 ────────────────────────────────────────────────

  pacing.rhythm:
    description: "컷 길이 분포가 style_profile 기준에서 크게 벗어나지 않음"
    applies_to: scene_durations
    measurement:
      method: duration_stddev_ratio
      max_stddev_ratio: 0.30           # 평균의 30% 이하 표준편차
    on_fail: warn
    severity: warning
    apo_weight: medium
```

---

### 6-2. Consistency Anchor

씬 생성 전 **앵커**를 scene_script.json에 명시한다.  
이후 생성된 씬들은 앵커 기준으로 일관성을 검증받는다.

```json
// scene_script.json 내 consistency_anchors 필드
{
  "consistency_anchors": {
    "character": {
      "reference_image": "assets/character_ref.png",
      "description": "20대 한국 여성, 갈색 웨이브 헤어, 베이지 니트 상의",
      "negative_prompt": "different hairstyle, different outfit, different person"
    },
    "background": {
      "style": "minimal_indoor_warm",
      "description": "따뜻한 조명, 흰 벽, 미니멀 인테리어",
      "color_palette": ["#FAF0E6", "#D4A574", "#FFFFFF"]
    },
    "voice": {
      "tts_voice_id": "elevenlabs_kr_female_01",
      "target_energy": "energetic_upbeat",
      "speed_wpm": 180
    },
    "subtitle": {
      "font": "Noto Sans KR Bold",
      "color": "#FFFFFF",
      "stroke": "#000000",
      "position": "center",
      "emphasis_color": "#FF6B9D"
    }
  }
}
```

---

### 6-3. Checker 실행 흐름

씬이 **생성될 때마다** 즉시 검증한다 — 전체 완성 후 한 번에 하지 않는다.

```
[Scene 1 생성] → consistency_anchors 최초 설정
                  (character.visual 앵커 이미지 = scene_1_frame.png)

[Scene 2 생성] → CLIP similarity(scene_2, anchor) = 0.91 → PASS
[Scene 3 생성] → CLIP similarity(scene_3, anchor) = 0.67 → FAIL
                  on_fail: flag_regenerate
                  → scene_3를 consistency 제약 강화 프롬프트로 재생성
                  → CLIP similarity(scene_3_v2, anchor) = 0.88 → PASS

[전체 완성] → consistency_report.json 생성
            → APO scorer로 전달 (consistency score 포함)
```

---

### 6-4. Consistency Report 포맷

```json
{
  "consistency_report": {
    "character.visual": {
      "status": "PASS",
      "method": "CLIP",
      "scores": [1.0, 0.91, 0.88, 0.87, 0.90],
      "threshold": 0.85,
      "regenerated_scenes": [3]
    },
    "voice.identity": {
      "status": "PASS",
      "voice_id": "elevenlabs_kr_female_01",
      "all_scenes_match": true
    },
    "voice.energy_level": {
      "status": "WARN",
      "rms_values": [0.72, 0.68, 0.85, 0.70, 0.69],
      "variance": 0.17,
      "threshold": 0.15
    },
    "subtitle.style": {
      "status": "PASS"
    },
    "pacing.rhythm": {
      "status": "PASS",
      "durations": [2.0, 2.3, 1.8, 2.5, 2.1],
      "stddev_ratio": 0.12
    }
  },
  "overall": {
    "errors": 0,
    "warnings": 1,
    "regenerations": 1
  }
}
```

---

### 6-5. Pipeline Integrity (JSON 로직 일관성)

Output Consistency와 별개로, JSON 스테이지 간 논리 무결성도 검증한다.

```yaml
# consistency/rules/pipeline_integrity.yaml
rules:
  - id: PI001  # total_duration == Σ scene durations
  - id: PI002  # segment_ratio 합산 == 1.0
  - id: PI003  # scenes[0].segment == "hook"
  - id: PI004  # ppl_present → ppl segment 존재
  - id: PI005  # assemble_plan scene 수 == scene_script scene 수
  - id: PI006  # all active_properties keys present in style_profile
```

실행 시점: 각 JSON 스테이지 출력 직후 (Stage 3 asset 생성 전).

---

### 6-6. 검증 게이트 전체 위치

```
파이프라인 실행:
  eval/runner.py → FAIL이면 실행 차단

  [Stage 1: analyze] → style_profile.json
      schema validation
      pipeline_integrity (PI006: property contract)

  [Stage 2: script] → scene_script.json
      schema validation
      pipeline_integrity (PI001~PI005)
      consistency_anchors 확정 → assets/에 저장

  [Stage 3: assemble]
      씬별 생성 → Output Consistency 즉시 검증
        FAIL → 재생성 (max_retry: 2)
      최종 assembly
      consistency_report.json 생성

  APO 후보 검증:
      eval/runner.py (fixture) → PASS
      pipeline_integrity → error 0
      Output Consistency → error 0
      → HITL 게이트 진입
```

---

## 7. 중간 산출물 스키마

### style_profile.json (analyze 출력)

```json
{
  "channel": "@AmyGlamy",
  "hook": {
    "type": "question",
    "position_sec": 1.8,
    "pattern_example": "girly들 썸탈 때 제일 중요한게 뭔지 알아?"
  },
  "cuts": {
    "avg_duration_sec": 2.1,
    "rhythm_pattern": "fast-open"
  },
  "subtitle": {
    "sync_tightness": "tight",
    "emphasis_style": "color_change",
    "position": "center"
  },
  "bgm": {
    "entry_sec": 0,
    "duck_on_speech": true,
    "genre": "upbeat-kpop-adjacent"
  },
  "narrative": {
    "target_persona": "girly",
    "ppl_present": true,
    "ppl_bridge_phrase": "내가 요즘 꼭 챙겨다니는 거",
    "segment_ratio": {
      "hook": 0.07,
      "empathy": 0.35,
      "tip": 0.25,
      "ppl": 0.25,
      "cta": 0.08
    },
    "direct_address_style": "girly❤️"
  }
}
```

### scene_script.json (script 출력)

```json
{
  "prompt": "사용자 입력 프롬프트 원문",
  "total_duration_sec": 38,
  "scenes": [
    {
      "id": 1,
      "segment": "hook",
      "duration_sec": 2.0,
      "voiceover": "썸남 100% 꼬시는 법 알려줄게",
      "subtitle": "썸남 100% 꼬시는 법 알려줄게",
      "subtitle_emphasis": ["100%"],
      "visual_direction": "정면 직캠, 자신감 있는 표정",
      "bgm_cue": "fade_in"
    },
    {
      "id": 2,
      "segment": "empathy",
      "duration_sec": 8.0,
      "voiceover": "...",
      "subtitle": "...",
      "visual_direction": "...",
      "bgm_cue": "continue"
    }
  ],
  "bgm": "upbeat-kpop-inst",
  "hashtags": ["#썸", "#연애팁", "#뷰티"]
}
```

---

## 7. 디렉토리 구조

```
shortform-harness/
│
├── harness.yaml                         ← [L2] 스테이징 설정
│
├── properties/                          ← Property 시스템
│   ├── registry.yaml                    ← 전역 property 카탈로그
│   ├── presets/
│   │   ├── lifestyle_kr.yaml
│   │   └── product_review.yaml
│   └── custom/
│       └── amyglamy.yaml
│
├── templates/                           ← [L1] Prompt Template Library
│   ├── analyze/
│   │   ├── v1.yaml
│   │   └── v2.yaml
│   ├── script/
│   │   ├── v1.yaml
│   │   └── v2.yaml
│   └── assemble/
│       └── v1.yaml
│
├── schemas/                             ← 출력 JSON 스키마 (eval 기준)
│   ├── style_profile.schema.json
│   ├── scene_script.schema.json
│   └── assemble_plan.schema.json
│
├── eval/                                ← [L1] Template Eval (fixture 기준)
│   ├── runner.py
│   ├── fixtures/
│   │   ├── analyze/
│   │   │   └── amyglamy_001.json        ← { input, expected_output }
│   │   ├── script/
│   │   │   └── case_001.json
│   │   └── assemble/
│   │       └── case_001.json
│   └── validators/
│       └── schema.py
│
├── consistency/                         ← Output Consistency + Pipeline Integrity
│   ├── checker.py                       ← 통합 실행기
│   ├── properties.yaml                  ← property별 일관성 정의
│   └── rules/
│       └── pipeline_integrity.yaml      ← JSON 로직 무결성 규칙
│
├── feedback/                            ← [L3] APO 입력
│   └── rubric.yaml
│
├── apo/                                 ← [L3] Optimization Engine
│   ├── scorer.py
│   ├── optimizer.py
│   ├── candidates/
│   └── history/
│       └── runs.jsonl
│
├── pipeline/                            ← [L2] 실행 레이어
│   ├── loader.py                        ← harness.yaml → 활성 템플릿 + property 조합
│   ├── analyze.py
│   ├── script.py
│   ├── assemble.py
│   └── extractors.py                    ← extract_method 구현체
│
├── data/                                ← 런타임 중간 산출물
│   ├── style_profile.json
│   └── scene_script.json
│
├── outputs/                             ← 생성된 영상
│   ├── video_01.mp4
│   ├── video_02.mp4
│   └── prompts.md
│
└── run.sh                               ← 전체 파이프라인 1-command 실행
```

---

## 8. 기술 스택

| 도구 | 용도 | 선택 이유 |
|------|------|----------|
| `yt-dlp` | 레퍼런스 영상 다운로드 | 무료, 안정적 CLI |
| `ffmpeg` | 장면 분할·오디오 추출·최종 편집 | 업계 표준, 프로그래매틱 제어 |
| `openai-whisper` | STT + 타임스탬프 추출 | 한국어 정확도, 오픈소스 |
| `Claude API` | 스타일 분석 + 스크립트 생성 + APO | JSON mode, 한국어 품질 |
| `ElevenLabs` | 한국어 TTS | 자연스러운 억양, REST API |
| `HeyGen` | AI 아바타 영상 생성 | 1인 직캠 스타일 재현 |
| `moviepy` + `PIL` | 자막 렌더링·컷 조합 | Python 통합, 세밀한 제어 |

**왜 Kling/RunwayML 전체 생성이 아닌가:**
- 스타일 파라미터(컷 길이, 자막 타이밍)를 프로그래매틱으로 제어 불가
- style_profile.json 값이 실제 결과에 반영되는지 검증 어려움
- HeyGen + moviepy 조합이 분석↔생성 분리 원칙에 부합

---

## 9. 구현 우선순위 (Cut-line)

| 우선순위 | 유지 | 포기 가능 |
|---------|------|----------|
| P0 | `properties/registry.yaml` + `custom/amyglamy.yaml` | — |
| P0 | `templates/` 3개 스테이지 v1 | v2 이상 버전 |
| P0 | `eval/runner.py` + 1개 fixture per stage | 다수 fixture |
| P1 | `harness.yaml` + `pipeline/loader.py` | — |
| P1 | `pipeline/analyze.py` + `script.py` | `assemble.py` 완전 자동화 |
| P2 | 영상 2편 (동일 시스템, 다른 프롬프트) | 영상 품질 |
| P3 | `apo/scorer.py` + `feedback/rubric.yaml` | `apo/optimizer.py` |

---

## 10. 제출물 체크리스트

```
□ README.md        — 실행 방법, 아키텍처 다이어그램
□ analysis.md      — 레퍼런스 분석 (바이럴 포인트, 재현 판단, 미재현 이유)
□ retro.md         — 가설, 막힌 지점, 사용 모델, 개선점
□ harness.yaml     — 스테이징 설정
□ templates/       — 3 스테이지 × v1
□ properties/      — registry + preset + custom
□ eval/            — runner + fixtures
□ data/*.json      — 중간 산출물 예시 (style_profile, scene_script)
□ outputs/*.mp4    — 생성 영상 2편 이상
□ outputs/prompts.md — 사용 프롬프트 원문
```
