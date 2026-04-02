# 2026-03-19 세션 작업 요약

> 브랜치: wan/test
> 세션 범위: ComfyUI 어댑터 구현 → Gemini 연동 → 대시보드 서버 구현

---

## 1. 세션 목표

Engine의 animate 파이프라인에서 **실제 WAN I2V 모션 생성**이 가능하도록 하고,
sprite_gen 대시보드를 engine 백엔드로 교체하여 **프론트엔드까지 통합**.

---

## 2. 커밋 이력

| # | 커밋 | 설명 |
|---|------|------|
| 1 | `bea8dc1` | `chore: uv.lock 갱신` |
| 2 | `5b61df7` | `feat: ComfyUI 어댑터 구현` — 3파일(446줄) + Hydra YAML + 워크플로우 |
| 3 | `2a9e6f6` | `fix: animate CLI 실행 경로 연결` — PipelineConfig extra, raw config, load() |
| 4 | `69e5810` | `feat: Gemini 어댑터 4개 YAML + 전체 연동 프로필` |
| 5 | `ced2c9e` | `feat: engine 대시보드 서버` — Flask 3파일(490줄) + adapters YAML 전환 |
| 6 | `d79ecc0` | `chore: .gitignore에 .env 추가` |

---

## 3. 완료된 작업

### 3.1 ComfyUI 어댑터 구현 (커밋 2-3)

**문제**: `AnimationGenerationPort`에 `DummyAnimationGenerator`만 존재. 실제 모션 생성 불가.

**해결**: sprite_gen의 `ComfyUIClient`를 헥사고널 아키텍처에 맞게 3파일로 포팅.

| 파일 | 줄수 | 역할 |
|------|------|------|
| `comfyui_client.py` | 180 | HTTP 전송 (upload, queue, poll, download, free) |
| `comfyui_workflow.py` | 141 | 워크플로우 로드 + GUI→API 변환 + 파라미터 주입 |
| `comfyui_wan_generator.py` | 125 | AnimationGenerationPort 구현체 |

**추가 수정 3건** (CLI 실행 경로 연결):
- `PipelineConfig`/`AnimatePipelineConfig` → `extra="ignore"` (animate 키 허용)
- `animate_pipeline` subflow에서 raw Hydra config 재compose
- `build_animate_context`에서 load() 라이프사이클 호출

**E2E 결과**: 480x480 / 64프레임 / 4초 / 449KB MP4 / 284초 (RTX 5070 Ti)

### 3.2 Gemini 연동 (커밋 4)

**문제**: Gemini 어댑터 코드 4개는 이미 존재했으나, Hydra YAML 설정이 없음.

**해결**: YAML 4개 생성 + `GEMINI_API_KEY` 환경변수로 ModelHandle 전달.

| 포트 | YAML |
|------|------|
| ModeClassificationPort | `conf/models/mode_classifier/gemini.yaml` |
| VisionAnalysisPort | `conf/models/vision_analyzer/gemini.yaml` |
| AIValidationPort | `conf/models/ai_validator/gemini.yaml` |
| PostMotionClassificationPort | `conf/models/post_motion_classifier/gemini.yaml` |

**E2E 결과**: Gemini + ComfyUI 전체 연동 / 7 attempt 리트라이 루프 / 33.5분 / Gemini API 전체 200 OK

### 3.3 대시보드 서버 구현 (커밋 5)

**문제**: sprite_gen 대시보드(wan_dashboard.html)를 engine에서 사용하려면 백엔드 교체 필요.

**해결**: Flask 서버 3파일(490줄) + animate_adapters YAML 5개 Dummy→실제 전환.

| 파일 | 줄수 | 역할 |
|------|------|------|
| `engine_server.py` | 189 | Flask app + 핵심 API (classify, generate, status, videos) |
| `engine_server_extra.py` | 158 | 추가 API (select_video, classify_motion, export, stats) |
| `engine_server_helpers.py` | 143 | 유틸리티 (video_list, serve_media, browse_dir, parse_stats) |

**animate_adapters 전환** (코드 변경 없이 YAML만):

| 어댑터 | Dummy → 실제 |
|--------|-------------|
| bg_remover | `DummyBgRemover` → `FfmpegBgRemover` (97줄) |
| format_converter | `DummyFormatConverter` → `MultiFormatConverter` (156줄) |
| keyframe_generator | `DummyKeyframeGenerator` → `PilKeyframeGenerator` (154줄) |
| numerical_validator | `DummyAnimationValidator` → `NumericalAnimationValidator` (125줄) |
| mask_generator | `DummyMaskGenerator` → `PilMaskGenerator` |

**CLI 커맨드 추가**:
```bash
uv run discoverex serve --port 5001 --config-name animate_comfyui
```

### 3.4 환경 설정 (커밋 6)

- `~/engine/.env` 생성 (`GEMINI_API_KEY`, `COMFYUI_URL`)
- `.gitignore`에 `.env` 추가 (API 키 커밋 방지)

---

## 4. WAN 모델 스택

| 노드 | 모델 파일 | 역할 |
|------|----------|------|
| UnetLoaderGGUF | `wan2.1-i2v-14b-480p-Q3_K_S.gguf` | WAN 2.1 I2V 14B, GGUF Q3_K_S |
| CLIPLoader | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | UMT5-XXL 텍스트 인코더 |
| CLIPVisionLoader | `clip_vision_h.safetensors` | CLIP Vision H 이미지 인코더 |
| VAELoader | `wan_2.1_vae.safetensors` | WAN 2.1 VAE 디코더 |

---

## 5. 전체 아키텍처 (현재 상태)

```
브라우저 (wan_dashboard.html, 5단계 UI)
    ↓ HTTP REST (15개 API)
engine_server.py (Flask, port 5001)
    ↓
AnimateOrchestrator (build_animate_context)
    ├── GeminiModeClassifier        ← Gemini 2.5 Flash
    ├── GeminiVisionAnalyzer        ← Gemini 2.5 Flash
    ├── ComfyUIWanGenerator         ← ComfyUI HTTP API (port 8188)
    ├── NumericalAnimationValidator  ← 8개 메트릭 검증
    ├── GeminiAIValidator           ← Gemini 2.5 Flash
    ├── GeminiPostMotionClassifier  ← Gemini 2.5 Flash
    ├── FfmpegBgRemover             ← ffmpeg + flood-fill
    ├── PilMaskGenerator            ← PIL
    ├── PilKeyframeGenerator        ← 물리 기반 키프레임
    └── MultiFormatConverter        ← APNG/WebM/Lottie
```

---

## 6. 검증 결과

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success |
| 200줄 제약 | 0건 위반 |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
| ComfyUI E2E (Dummy) | **성공** — 449KB MP4, 284초 |
| Gemini + ComfyUI E2E | **동작** — 7 attempt, 33.5분, Gemini 전체 200 OK |

---

## 7. 신규 파일 목록

### 커밋 2 — ComfyUI 어댑터
```
src/discoverex/adapters/outbound/models/comfyui_client.py
src/discoverex/adapters/outbound/models/comfyui_workflow.py
src/discoverex/adapters/outbound/models/comfyui_wan_generator.py
conf/models/animation_generation/comfyui.yaml
conf/workflows/wan21_i2v.json
COMFYUI_ADAPTER_REPORT.md
```

### 커밋 3 — CLI 실행 경로 연결
```
conf/animate_comfyui.yaml
conf/flows/animate/comfyui_pipeline.yaml
```

### 커밋 4 — Gemini YAML
```
conf/models/mode_classifier/gemini.yaml
conf/models/vision_analyzer/gemini.yaml
conf/models/ai_validator/gemini.yaml
conf/models/post_motion_classifier/gemini.yaml
COMFYUI_E2E_REPORT.md
```

### 커밋 5 — 대시보드 서버
```
src/discoverex/adapters/inbound/web/__init__.py
src/discoverex/adapters/inbound/web/engine_server.py
src/discoverex/adapters/inbound/web/engine_server_extra.py
src/discoverex/adapters/inbound/web/engine_server_helpers.py
conf/animate_adapters/bg_remover/real.yaml
conf/animate_adapters/format_converter/real.yaml
conf/animate_adapters/keyframe_generator/real.yaml
conf/animate_adapters/numerical_validator/real.yaml
conf/animate_adapters/mask_generator/real.yaml
ENGINE_DASHBOARD_REPORT.md
```

---

## 8. 사용 방법

```bash
# CLI 모드 (배치/자동화)
export $(grep -v '^#' .env | xargs)
uv run discoverex animate --image-path <sprite.png> --config-name animate_comfyui

# 대시보드 모드 (개발/디버그)
export $(grep -v '^#' .env | xargs)
uv run discoverex serve --port 5001 --config-name animate_comfyui
# → http://localhost:5001/
```

---

## 9. 수정된 기존 파일

| 파일 | 커밋 | 변경 |
|------|------|------|
| `src/discoverex/config/schema.py` | 3 | PipelineConfig extra="forbid" → "ignore" |
| `src/discoverex/config/animate_schema.py` | 3 | AnimatePipelineConfig extra="forbid" → "ignore" |
| `src/discoverex/config_loader.py` | 3 | `load_raw_animate_config()` 추가 |
| `src/discoverex/flows/subflows.py` | 3 | raw config 재compose 로직 |
| `src/discoverex/bootstrap/factory.py` | 3,4 | load() 라이프사이클 + GEMINI_API_KEY ModelHandle |
| `src/discoverex/adapters/inbound/cli/main.py` | 5 | `serve` 커맨드 추가 |
| `conf/animate_comfyui.yaml` | 4,5 | Gemini+ComfyUI+실제 어댑터 전체 프로필 |
| `.gitignore` | 6 | .env 추가 |
