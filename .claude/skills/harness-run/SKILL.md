# Skill: harness-run

숏폼 영상 생성 파이프라인을 API 키 없이 실행한다.
Claude Code 자체가 LLM 스테이지(Stage 1·2)를 직접 수행하고, 결정론적 스테이지(Stage 5·6)는 스크립트로 실행한다.

## 트리거

사용자가 다음과 같이 요청할 때 이 스킬을 실행한다:
- `harness run "<프롬프트>"`
- `/harness-run <프롬프트>`
- `"<주제> 숏폼 만들어"`

## 실행 절차

### 0. Run ID 결정
```
run_id = "run_YYYYMMDD_NNN"   # 날짜 + 당일 순번 (data/runs/ 기존 목록 확인)
run_dir = data/runs/{run_id}/
```
`data/runs/` 디렉토리를 확인해 당일 마지막 번호 다음으로 설정한다.

---

### Stage 1 — Story Parser (Claude 직접 실행)

`templates/story_parser/v1.yaml`의 system/user 프롬프트를 읽어,
Claude가 직접 `beat_structure.json`을 생성한다.

**출력 스키마** (`schemas/beat_structure.schema.json` 준수):
```json
{
  "total_duration_sec": 30,
  "target_persona": "girly",
  "emotional_arc": "curiosity→empathy→solution→desire→action",
  "beats": [
    {"id": 1, "function": "hook",          "duration_ratio": 0.08, "energy": "high",   "description": "..."},
    {"id": 2, "function": "empathy",       "duration_ratio": 0.20, "energy": "medium", "description": "..."},
    {"id": 3, "function": "tip",           "duration_ratio": 0.37, "energy": "medium", "description": "..."},
    {"id": 4, "function": "product_focus", "duration_ratio": 0.20, "energy": "medium", "description": "..."},
    {"id": 5, "function": "cta",           "duration_ratio": 0.15, "energy": "high",   "description": "..."}
  ]
}
```

`duration_ratio` 합계가 반드시 1.0이어야 한다.

파일 저장: `data/runs/{run_id}/beat_structure.json`

---

### Stage 2 — Scene Planner (Claude 직접 실행)

`templates/scene_planner/v1.yaml` + `data/style_profile.json`을 참조하여,
beat_structure를 바탕으로 Claude가 직접 `scene_grammar.json`을 생성한다.

**핵심 규칙**:
- `scenes[*].duration` 합계 = `total_duration_sec` (30.0)
- hook scene duration ≤ 2.5s
- `consistency_anchors`는 `data/style_profile.json` 값 그대로 사용
- 각 씬의 `voiceover`는 자연스러운 한국어 구어체
- `visual_prompt`는 `consistency_anchors.character.description` + `consistency_anchors.background.description`을 반드시 포함

파일 저장: `data/runs/{run_id}/scene_grammar.json`

---

### Stage 5 — Pacing Engine (스크립트)

```bash
python3 -c "
import sys, json
sys.path.insert(0, '.')
from pathlib import Path
from pipeline.pacing_engine import run as pacing_run
from pipeline.loader import load_harness

grammar = json.loads(Path('data/runs/{run_id}/scene_grammar.json').read_text())
harness = load_harness()
manifest = pacing_run(grammar, harness)
Path('data/runs/{run_id}/timing_manifest.json').write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2)
)
print('✓ timing_manifest.json')
"
```

---

### Stage 6 — Placeholder Video (스크립트)

```bash
python3 scripts/make_placeholder_video.py {run_id}
```

출력: `outputs/{run_id}.mp4` (1080×1920, 30s, 30fps)

---

## 완료 보고

스킬 완료 후 다음을 보고한다:
- run_id
- 생성된 씬 목록 (id, scene_type, duration)
- 영상 경로 및 크기
- hashtags
