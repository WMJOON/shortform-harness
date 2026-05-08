# Shortform Video Generation Harness

텍스트 프롬프트 하나를 받아 레퍼런스 숏폼 영상의 스타일을 재현하는 재사용 가능한 생성 파이프라인.

---

## 핵심 철학

> We do not generate a full video directly.  
> Instead, we decompose narrative into scene beats → generate scenes independently → re-compose using pacing constraints → apply style-consistent subtitle/cut rules.

숏폼은 "영상"이 아니라 **attention rhythm assembly**다.  
레퍼런스 영상의 스타일 핵심은 frame quality가 아니라 **cut sequencing**에 있다:

- 0~2초 hook
- reaction cut + zoom timing
- subtitle burst on emphasis
- emotional beat → pacing transition

따라서 시스템의 목표는 "영상 생성"이 아니라 **Scene Grammar를 생성하고 조립**하는 것이다.

---

## 아키텍처

```
[입력] 텍스트 프롬프트
    ↓
┌─────────────────────┐
│  1. Story Parser    │  LLM → beat_structure.json
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│  2. Scene Planner   │  LLM → scene_grammar.json  ← 핵심 중간 표현
└──────────┬──────────┘
           ↓
    ┌──────┴──────┐
    ↓             ↓
┌──────────┐  ┌──────────────────┐
│ 3. Scene │  │ 4. Subtitle      │   병렬 실행
│ Generator│  │    Generator     │
│(Kling /  │  │ (ElevenLabs TTS) │
│ GPT-img2)│  └──────────────────┘
└──────────┘
    ↓ scene_assets/ + subtitle_tracks/
    └──────┬──────────────────┘
           ↓
┌─────────────────────┐
│  5. Pacing Engine   │  rule-based → timing_manifest.json
└──────────┬──────────┘
           ↓
┌─────────────────────┐
│  6. Video Composer  │  ffmpeg → output.mp4 (1080×1920, 9:16)
└─────────────────────┘
```

### 4-Layer 시스템

```
Layer 4: APO (Automatic Prompt Optimization)
         rubric 채점 → meta-prompt → 후보 템플릿 → HITL Gate → 승격

Layer 3: Orchestrator Agent (Claude API tool_use)
         실행 계획 / Prompt Registry / Run State / 씬 단위 재생성

Layer 2: Template Staging (harness.yaml)
         스테이지별 활성 템플릿 버전 결정 / A·B 후보 관리

Layer 1: Prompt Template Library
         templates/{stage}/v1.yaml — eval_cases 내장, 독립 파일
```

---

## 빠른 시작

### 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

환경 변수 설정:

```bash
export ANTHROPIC_API_KEY=sk-...
export ELEVENLABS_API_KEY=...   # TTS 사용 시
export KLING_API_KEY=...        # 영상 생성 시
```

### 실행

```bash
# 기본 실행
harness run "썸남 꼬시는 뷰티 루틴"

# 커스텀 스타일 + 길이
harness run "피부 트러블 진정 루틴" --preset lifestyle_kr --custom amyglamy --duration 30

# dry-run (scene_grammar까지만, API 호출 없음)
harness run "..." --dry-run

# 중단된 Run 재개
harness run "..." --resume run_20260508_001

# 특정 스테이지부터 재개
harness run "..." --from-stage scene_generator

# 오케스트레이터 대화 모드
harness run "뷰티 루틴" --chat
```

### Prompt Registry

```bash
harness registry list --stage scene_planner --tags lifestyle_kr
harness registry save --run run_001 --stage scene_planner --score 8.5 --tags lifestyle_kr ppl
```

### 템플릿 Eval

```bash
harness eval                         # 전체 eval_cases 실행
harness eval --stage story_parser    # 특정 스테이지만
```

---

## 프로젝트 구조

```
shortform-harness/
├── harness.yaml                    ← 스테이징 설정 (활성 템플릿 + 백엔드)
│
├── pipeline/                       ← 6단계 파이프라인 구현
│   ├── llm.py                      ← 공유 LLM 헬퍼 (call_llm, render_messages)
│   ├── constants.py                ← BeatFunction / SceneType / SubtitleDensity
│   ├── loader.py                   ← harness.yaml → 활성 템플릿 + properties 로드
│   ├── story_parser.py             ← Stage 1: prompt → beat_structure
│   ├── scene_planner.py            ← Stage 2: beats → scene_grammar
│   ├── scene_generator.py          ← Stage 3: 씬별 병렬 비주얼 생성
│   ├── subtitle_generator.py       ← Stage 4: voiceover → subtitle_timing
│   ├── pacing_engine.py            ← Stage 5: rule-based timing_manifest (LLM 없음)
│   └── video_composer.py           ← Stage 6: ffmpeg 합성
│
├── orchestrator/
│   ├── agent.py                    ← tool_use 루프 오케스트레이터
│   ├── tools.py                    ← 12개 파이프라인·레지스트리 도구
│   └── system_prompt.md
│
├── templates/                      ← Prompt Template Library
│   ├── story_parser/v1.yaml
│   ├── scene_planner/v1.yaml
│   ├── scene_generator/v1.yaml
│   └── subtitle_generator/v1.yaml
│
├── schemas/                        ← JSON Schema (스테이지 간 계약)
│   ├── beat_structure.schema.json
│   ├── scene_grammar.schema.json   ← 핵심 중간 표현
│   ├── generation_request.schema.json
│   └── timing_manifest.schema.json
│
├── properties/                     ← Property 시스템
│   ├── registry.yaml               ← 전역 property 카탈로그
│   ├── presets/lifestyle_kr.yaml   ← 한국 라이프스타일 기본 preset
│   └── custom/amyglamy.yaml        ← @AmyGlamy 레퍼런스 override
│
├── eval/
│   ├── runner.py                   ← eval_cases 실행기
│   └── fixtures/                   ← 스테이지별 입출력 fixture
│
├── consistency/
│   ├── checker.py                  ← PI001-PI006 + property 일관성 검사
│   ├── properties.yaml             ← CLIP·RMS·config_exact 측정 정의
│   └── rules/pipeline_integrity.yaml
│
├── apo/
│   ├── scorer.py                   ← rubric 가중 채점 (0~10점)
│   └── optimizer.py                ← meta-prompt → 후보 템플릿 생성
│
├── feedback/rubric.yaml            ← 5개 평가 차원 (hook·cut_rhythm·subtitle·ppl·human)
├── registry/prompts/entries.jsonl  ← 저장된 프롬프트 목록
├── data/style_profile.json         ← 레퍼런스 분석 결과 (재사용)
└── cli.py                          ← typer CLI 진입점
```

---

## Scene Grammar — 핵심 중간 표현

모든 파이프라인 스테이지가 `scene_grammar.json` 하나를 통해 소통한다.

```json
{
  "narrative": { "total_duration_sec": 30, "target_persona": "girly", "emotional_arc": "..." },
  "scenes": [
    {
      "id": 1, "scene_type": "hook", "duration": 2.0,
      "camera": "selfie-close", "zoom": false,
      "voiceover": "트러블 때문에 맨날 쿨링패드만 붙이고 있는 girly 있어?",
      "visual_prompt": "Korean woman ... tight close-up selfie ...",
      "bgm_cue": "fade_in", "transition_out": "smash-cut"
    }
  ],
  "consistency_anchors": {
    "character": { "description": "...", "negative_prompt": "..." },
    "background": { "style": "modern minimalist Korean apartment interior", "description": "..." },
    "voice": { "tts_voice_id": "elevenlabs_kr_female_01", "speed_wpm": 180 },
    "subtitle": { "font": "Noto Sans KR Bold", "color": "#FFFFFF", "position": "bottom" }
  }
}
```

`consistency_anchors`는 모든 씬의 `visual_prompt`에 반드시 포함된다.  
Pacing Engine은 이 JSON만 보고 `timing_manifest.json`을 결정론적으로 생성한다.

---

## Property 시스템

코드 변경 없이 스타일 파라미터를 추가·override한다.

```
registry.yaml           ← 전역 property 카탈로그 (maps_to 필드로 파이프라인 반영 경로 지정)
presets/lifestyle_kr.yaml  ← 장르 묶음 + 가중치
custom/amyglamy.yaml    ← 레퍼런스별 override + 커스텀 property
```

각 property의 `maps_to` 필드가 어느 파이프라인 출력의 어느 필드를 채우는지 결정한다.

---

## 검증 레이어

| 시스템 | 질문 | 실행 시점 |
|--------|------|-----------|
| `schemas/` | JSON 형식이 맞는가? | 각 스테이지 출력 직후 |
| `eval/runner.py` | 템플릿이 fixture 기준 출력을 내는가? | 파이프라인 진입 전 |
| `consistency/checker.py` | Scene Grammar ↔ Pacing이 서로 맞는가? | Stage 2·5 직후 |
| `consistency/checker.py` | 씬 자산이 property별로 일관된가? | Stage 3 씬별 즉시 |
| `apo/scorer.py` | 영상이 레퍼런스 스타일에 얼마나 가까운가? | 영상 완성 후 |

---

## 기술 스택

| 도구 | 용도 |
|------|------|
| Claude API | Story Parser · Scene Planner · APO (Orchestrator) |
| GPT Image 2 | Scene 이미지 생성 (9:16, 한국어 텍스트) |
| Kling AI | 이미지 → 영상 (Character Reference로 일관성 유지) |
| ElevenLabs | 한국어 TTS |
| ffmpeg | 씬 합성 · 자막 burn-in · BGM 믹싱 |
| typer + rich | CLI + TUI 진행 화면 |

---

## 라이선스

Private repository. 무단 배포 금지.
