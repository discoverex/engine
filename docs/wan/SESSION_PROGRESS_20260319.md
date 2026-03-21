# 2026-03-19 세션 진행 내용 (최종)

> 브랜치: wan/test
> 총 커밋: 21개

---

## 커밋 이력

| # | 커밋 | 구분 | 설명 |
|---|------|------|------|
| 1 | `bea8dc1` | chore | uv.lock 갱신 |
| 2 | `5b61df7` | **feat** | ComfyUI 어댑터 구현 (3파일 446줄) |
| 3 | `2a9e6f6` | fix | animate CLI 실행 경로 연결 |
| 4 | `69e5810` | **feat** | Gemini 어댑터 4개 YAML + 전체 연동 프로필 |
| 5 | `ced2c9e` | **feat** | engine 대시보드 서버 (Flask 3파일 490줄) |
| 6 | `d79ecc0` | chore | .gitignore에 .env 추가 |
| 7 | `d4aabef` | docs | 세션 작업 요약 v1 |
| 8 | `914176a` | fix | 비디오 목록/서빙 — glob 패턴 + CWD 경로 |
| 9 | `9c56329` | **feat** | 모델 선택 → ComfyUI 워크플로우 전달 |
| 10 | `0b954cc` | **feat** | 설치된 모델만 대시보드 표시 |
| 11 | `d09c8bc` | feat | 모델 VRAM 요구량 표시 |
| 12 | `1325c3f` | feat | 프로그레스 바 표시 (초기 구현) |
| 13 | `0edbdb4` | **feat** | 상세 실행 로그 + validation_stats.txt 기록 |
| 14 | `f9e70af` | docs | 세션 작업 요약 v2 |
| 15 | `517498f` | fix | 워크플로우 로그에 모델명 표시 |
| 16 | `b3dd478` | **feat** | orchestrator 상세 로그 (Stage1 + Vision 전체) |
| 17 | `a28fe67` | fix | 기존 영상 덮어쓰기 방지 — attempt offset |
| 18 | `8539aac` | docs | 세션 최종 요약 |
| 19 | `c4bd265` | **feat** | 이력 기반 negative 강화 |
| 20 | `7902f3f` | docs | 이력 강화 기능 보고서 |
| 21 | `ce6f417` | fix | 프로그레스 바 — /queue 기반으로 전환 |

---

## 주요 기능별 상세

### 1. ComfyUI 어댑터 (커밋 2-3)

sprite_gen의 ComfyUIClient를 헥사고널 아키텍처로 포팅.

- `comfyui_client.py` (198줄) — HTTP 전송
- `comfyui_workflow.py` (143줄) — 워크플로우 로드 + 파라미터 주입
- `comfyui_wan_generator.py` (127줄) — AnimationGenerationPort 구현체
- E2E: 480x480 / 64프레임 / 4초 / 449KB MP4 / 284초

### 2. Gemini 연동 (커밋 4)

YAML 4개 + GEMINI_API_KEY ModelHandle 전달.

- mode_classifier, vision_analyzer, ai_validator, post_motion_classifier
- E2E: 7 attempt / 33.5분 / Gemini 전체 200 OK

### 3. 대시보드 서버 (커밋 5, 8)

Flask 서버 3파일 + animate_adapters 실제 전환 + CLI `serve` 커맨드.

- `engine_server.py` (194줄) — 핵심 API
- `engine_server_extra.py` (171줄) — 추가 라우트
- `engine_server_helpers.py` (170줄) — 유틸리티
- `dashboard.html` — engine 전용 복사본
- 15개 API 엔드포인트

### 4. 프론트엔드 개선 (커밋 9-12, 21)

| 기능 | 커밋 | 내용 |
|------|------|------|
| 모델 선택 전달 | `9c56329` | UnetLoaderGGUF.unet_name 동적 주입 |
| 설치 모델만 표시 | `0b954cc` | /api/available_models + 동적 select |
| VRAM 요구량 | `d09c8bc` | 양자화별 VRAM 테이블 |
| 프로그레스 바 | `ce6f417` | /queue 기반 노드 진행률 → 프로그레스 바 |

#### 프로그레스 바 구현 변경 이력

| 단계 | 구현 | 문제 |
|------|------|------|
| 초기 (`1325c3f`) | ComfyUI `/progress` HTTP 호출 | `/progress` 엔드포인트 미존재 → 항상 null |
| 수정 (`ce6f417`) | `/queue` 폴링 → 실행 중 노드 수 기반 추정 | ComfyUIClient 클래스 변수로 공유 |

### 5. 로그 + 통계 (커밋 13, 15-17)

| 기능 | 내용 |
|------|------|
| 상세 터미널 로그 | 시도별 seed/fps, 수치/AI 검증, 보완 조치 |
| validation_stats.txt | sprite_gen 호환 형식 파일 기록 |
| orchestrator 로그 | Stage1 분류 + Vision 분석 전체 (오브젝트, 움직임, 프롬프트) |
| 워크플로우 로그 | 주입 시 모델명 표시 |
| 영상 덮어쓰기 방지 | 기존 파일 스캔 → attempt offset 자동 계산 |

### 6. 이력 기반 negative 강화 (커밋 19)

sprite_gen의 `_ValidationStats.load_history()` 로직 포팅.

- `load_history()` — validation_stats.txt 파싱 (정규식, 구/신 포맷 호환)
- `build_history_negative()` — 2회 이상 발생 이슈 → 중국어 negative 추출
- `ISSUE_NEGATIVE_MAP` 12개 (sprite_gen과 동일)
- `LoopState.history_negative` → `build_prompts()`에서 base_negative에 자동 추가
- 기존 sprite_gen 이력(281줄, 19장 102회)도 자동 반영

### 7. anim_pipeline 분리 (별도 커밋, dev 브랜치)

- `wan_server.py` 기본 포트 5001 → 5002 변경
- `wan_dashboard.html` API URL 자동 감지

---

## 설치된 WAN 모델

| 모델 | 크기 | VRAM |
|------|------|------|
| wan2.1-i2v-14b-480p-Q3_K_S.gguf | 7.4GB | 6.5GB |
| wan2.1-i2v-14b-480p-Q4_K_S.gguf | 9.8GB | 8.75GB |
| wan2.1-i2v-14b-480p-Q4_K_M.gguf | 11GB | 9.65GB |

---

## 실행 방법

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine 대시보드
cd ~/engine
export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui

# 터미널 3: anim_pipeline (필요 시)
cd ~/anim_pipeline && source animVenv/bin/activate
PYTHONPATH=. python image_pipeline/sprite_gen/wan_server.py

# 브라우저
# engine:        http://localhost:5001/
# anim_pipeline: http://localhost:5002/
```

---

## 검증

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success |
| 200줄 제약 | 0건 위반 |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
