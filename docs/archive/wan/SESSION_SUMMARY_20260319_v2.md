# 2026-03-19 세션 작업 요약 (v2)

> 브랜치: wan/test
> 세션 전체 범위: ComfyUI 어댑터 → Gemini 연동 → 대시보드 서버 → 프론트엔드 개선 → 로그/통계

---

## 1. 커밋 이력 (세션 전체)

| # | 커밋 | 설명 |
|---|------|------|
| 1 | `bea8dc1` | chore: uv.lock 갱신 |
| 2 | `5b61df7` | **feat: ComfyUI 어댑터 구현** — 3파일(446줄) |
| 3 | `2a9e6f6` | fix: animate CLI 실행 경로 연결 |
| 4 | `69e5810` | **feat: Gemini 어댑터 4개 YAML** + 전체 연동 프로필 |
| 5 | `ced2c9e` | **feat: engine 대시보드 서버** — Flask 3파일(490줄) |
| 6 | `d79ecc0` | chore: .gitignore에 .env 추가 |
| 7 | `d4aabef` | docs: 세션 작업 요약 v1 |
| 8 | `914176a` | fix: 대시보드 비디오 목록/서빙 수정 |
| 9 | `9c56329` | **feat: 프론트엔드 모델 선택 → ComfyUI 전달** |
| 10 | `0b954cc` | **feat: 설치된 모델만 대시보드 표시** |
| 11 | `d09c8bc` | feat: 모델 선택 시 VRAM 요구량 표시 |
| 12 | `1325c3f` | **feat: ComfyUI 생성 진행률 프로그레스 바** |
| 13 | `0edbdb4` | **feat: 상세 실행 로그 + validation_stats.txt** |

---

## 2. 완료된 작업 — 전체 요약

### Phase 1: ComfyUI 어댑터 (커밋 2-3)

sprite_gen의 ComfyUIClient를 engine 헥사고널 아키텍처로 포팅.

| 파일 | 줄수 | 역할 |
|------|------|------|
| `comfyui_client.py` | 180 | HTTP 전송 (upload, queue, poll, download, free) |
| `comfyui_workflow.py` | 141 | 워크플로우 로드 + GUI→API 변환 + 파라미터 주입 |
| `comfyui_wan_generator.py` | 125 | AnimationGenerationPort 구현체 |

E2E 결과: 480x480 / 64프레임 / 4초 / 449KB MP4 / 284초

### Phase 2: Gemini 연동 (커밋 4)

Gemini 어댑터 YAML 4개 + GEMINI_API_KEY ModelHandle 전달.

E2E 결과: 7 attempt 리트라이 루프 / 33.5분 / Gemini API 전체 200 OK

### Phase 3: 대시보드 서버 (커밋 5, 8)

Flask 서버 3파일(490줄) — sprite_gen의 wan_dashboard.html 서빙 + 15개 API.
animate_adapters YAML 5개 Dummy → 실제 구현체 전환.

### Phase 4: 프론트엔드 개선 (커밋 9-12)

| 기능 | 커밋 | 내용 |
|------|------|------|
| **모델 선택 전달** | `9c56329` | 프론트엔드 model_name → ComfyUI UnetLoaderGGUF.unet_name 주입 |
| **설치 모델만 표시** | `0b954cc` | `/api/available_models` API + 동적 select 생성 |
| **VRAM 요구량 표시** | `d09c8bc` | 양자화별 VRAM 추정값 표시 (`Q4_K_S (VRAM 8.75GB)`) |
| **진행률 프로그레스 바** | `1325c3f` | ComfyUI `/progress` → step/total/percent → 프로그레스 바 |

### Phase 5: 로그 + 통계 (커밋 13)

| 기능 | 내용 |
|------|------|
| **상세 터미널 로그** | 시도별 seed/fps, 수치 검증 결과, AI 검증 결과, 보완 조치 |
| **validation_stats.txt** | sprite_gen과 동일 형식으로 파일 기록 |
| **기존 이력 복사** | anim_pipeline의 stats (281줄, 19장 102회) → engine에 복사 |

---

## 3. 신규/수정 파일 전체 목록

### 신규 파일 (24개)

```
# ComfyUI 어댑터 (Phase 1)
src/discoverex/adapters/outbound/models/comfyui_client.py
src/discoverex/adapters/outbound/models/comfyui_workflow.py
src/discoverex/adapters/outbound/models/comfyui_wan_generator.py
conf/models/animation_generation/comfyui.yaml
conf/workflows/wan21_i2v.json

# Gemini YAML (Phase 2)
conf/models/mode_classifier/gemini.yaml
conf/models/vision_analyzer/gemini.yaml
conf/models/ai_validator/gemini.yaml
conf/models/post_motion_classifier/gemini.yaml

# 대시보드 서버 (Phase 3)
src/discoverex/adapters/inbound/web/__init__.py
src/discoverex/adapters/inbound/web/engine_server.py
src/discoverex/adapters/inbound/web/engine_server_extra.py
src/discoverex/adapters/inbound/web/engine_server_helpers.py
src/discoverex/adapters/inbound/web/dashboard.html

# animate_adapters 실제 YAML (Phase 3)
conf/animate_adapters/bg_remover/real.yaml
conf/animate_adapters/format_converter/real.yaml
conf/animate_adapters/keyframe_generator/real.yaml
conf/animate_adapters/numerical_validator/real.yaml
conf/animate_adapters/mask_generator/real.yaml

# Hydra 설정
conf/animate_comfyui.yaml
conf/flows/animate/comfyui_pipeline.yaml

# 로그/통계 (Phase 5)
src/discoverex/application/use_cases/animate/retry_logger.py

# 보고서
COMFYUI_ADAPTER_REPORT.md
COMFYUI_E2E_REPORT.md
ENGINE_DASHBOARD_REPORT.md
```

### 수정 파일 (8개)

| 파일 | 변경 |
|------|------|
| `src/discoverex/config/schema.py` | PipelineConfig extra="ignore" |
| `src/discoverex/config/animate_schema.py` | AnimatePipelineConfig extra="ignore" |
| `src/discoverex/config_loader.py` | `load_raw_animate_config()` 추가 |
| `src/discoverex/flows/subflows.py` | raw config 재compose |
| `src/discoverex/bootstrap/factory.py` | load() + GEMINI_API_KEY ModelHandle |
| `src/discoverex/adapters/inbound/cli/main.py` | `serve` 커맨드 추가 |
| `src/discoverex/application/use_cases/animate/retry_loop.py` | RetryLogger 연동 |
| `.gitignore` | .env 추가 |

---

## 4. 현재 아키텍처

```
브라우저 (dashboard.html, 5단계 UI)
    ↓ HTTP REST (15+ API)
engine_server.py (Flask, port 5001)
    ↓
AnimateOrchestrator
    ├── GeminiModeClassifier        ← Gemini 2.5 Flash
    ├── GeminiVisionAnalyzer        ← Gemini 2.5 Flash
    ├── ComfyUIWanGenerator         ← ComfyUI (port 8188)
    │   └── 모델 선택: Q3_K_S / Q4_K_S / Q4_K_M (프론트엔드에서 전환)
    ├── NumericalAnimationValidator  ← 8개 메트릭
    ├── GeminiAIValidator           ← Gemini 2.5 Flash
    ├── GeminiPostMotionClassifier  ← Gemini 2.5 Flash
    ├── FfmpegBgRemover             ← ffmpeg + flood-fill
    ├── PilMaskGenerator            ← PIL
    ├── PilKeyframeGenerator        ← 물리 기반 키프레임
    └── MultiFormatConverter        ← APNG/WebM/Lottie
```

---

## 5. 프론트엔드 개선 사항

| 기능 | 적용 전 | 적용 후 |
|------|---------|---------|
| 모델 선택 | 9개 하드코딩 | 설치된 모델만 동적 표시 |
| VRAM 정보 | 없음 | 각 모델 옆에 VRAM 요구량 표시 |
| 모델 전달 | 무시됨 | 선택한 모델로 ComfyUI 생성 |
| 생성 진행률 | "생성 중..." 텍스트만 | 프로그레스 바 + step/total 표시 |
| 비디오 표시 | 표시 안 됨 | glob 패턴 수정 + CWD 경로 resolve |

---

## 6. 설치된 WAN 모델

| 모델 | 파일 크기 | VRAM | 상태 |
|------|----------|------|------|
| wan2.1-i2v-14b-480p-Q3_K_S.gguf | 7.4GB | 6.5GB | 기존 설치 |
| wan2.1-i2v-14b-480p-Q4_K_S.gguf | 9.8GB | 8.75GB | 이번 세션 다운로드 |
| wan2.1-i2v-14b-480p-Q4_K_M.gguf | 11GB | 9.65GB | 이번 세션 다운로드 |

---

## 7. 검증 결과

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success |
| 200줄 제약 | 0건 위반 |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |

---

## 8. 실행 방법

```bash
# ComfyUI 서버 (터미널 1)
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# Engine 대시보드 (터미널 2)
cd ~/engine
export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui

# 브라우저 접속
# http://localhost:5001/
```
