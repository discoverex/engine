# ComfyUI 어댑터 E2E 테스트 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 커밋: 5b61df7 (어댑터 구현) + 2a9e6f6 (CLI 실행 경로 연결)

---

## 1. 요약

Engine의 animate 파이프라인에서 ComfyUI 어댑터를 통해 **실제 WAN I2V 비디오 생성에 성공**.
더미 결과(19바이트)가 아닌, 480x480 해상도 / 64프레임 / 4초 / 449KB의 실제 MP4 비디오를 생성.

---

## 2. 사용된 WAN 모델 스택

### 워크플로우: `conf/workflows/wan21_i2v.json`

| 노드 | 모델 파일 | 역할 |
|------|----------|------|
| UnetLoaderGGUF (node 16) | **wan2.1-i2v-14b-480p-Q3_K_S.gguf** | WAN 2.1 Image-to-Video 14B 파라미터, 480p, GGUF Q3_K_S 양자화 |
| CLIPLoader (node 2) | **umt5_xxl_fp8_e4m3fn_scaled.safetensors** | UMT5-XXL 텍스트 인코더 (FP8 양자화) |
| CLIPVisionLoader (node 4) | **clip_vision_h.safetensors** | CLIP Vision H 이미지 인코더 |
| VAELoader (node 3) | **wan_2.1_vae.safetensors** | WAN 2.1 전용 VAE 디코더 |

### 샘플링 설정 (KSampler, node 10)

| 파라미터 | 값 |
|----------|-----|
| Steps | 30 (워크플로우 기본값, engine에서 20으로 주입) |
| CFG | 6.5 |
| Sampler | euler_ancestral |
| Scheduler | normal |
| Denoise | 1.0 |

### 비디오 생성 설정 (WanImageToVideo, node 9)

| 파라미터 | 값 |
|----------|-----|
| Width | 480 |
| Height | 480 |
| Length (frames) | 33 |
| Batch Size | 1 |

### 비디오 출력 설정 (VHS_VideoCombine, node 12)

| 파라미터 | 값 |
|----------|-----|
| Format | video/h264-mp4 |
| Pixel Format | yuv420p |
| CRF | 19 |
| Frame Rate | 18 (워크플로우 기본값, engine에서 16으로 주입) |

---

## 3. E2E 실행 결과

### 실행 명령

```bash
uv run discoverex animate \
  --image-path ~/ComfyUI/input/fish_with_room_processed.png \
  --config-name animate_comfyui \
  --verbose
```

### 실행 로그

```
[ComfyUI] loaded: url=http://127.0.0.1:8188 workflow=conf/workflows/wan21_i2v.json client_id=engine_10749
[Animate] start: fish_with_room_processed
[Stage1] mode=motion_needed
[Preprocess] 480x480 -> 480x480 (원본유지)
[Animate] action=wing flap
[ComfyUI] image uploaded: fish_with_room_processed_processed.png
[Workflow] GUI format detected -> converting to API format
[Workflow] injected: seed=2911023781 steps=20 fps=16 480x480
[ComfyUI] queued: prompt_id=3bf44bbe-af91-4ea2-baa7-30d1f8bef9f0
[ComfyUI] generating… 30s elapsed
...
[ComfyUI] generating… 270s elapsed
[ComfyUI] generation complete (284.2s)
[ComfyUI] video downloaded: artifacts/animate/motion/fish_with_room_processed_processed_a1.mp4
engine entry completed command=animate in 285.09s

status: success
```

### 생성된 비디오 메타데이터

| 항목 | 값 |
|------|-----|
| 파일 | `artifacts/animate/motion/fish_with_room_processed_processed_a1.mp4` |
| 코덱 | H.264 |
| 해상도 | 480x480 |
| 프레임 수 | 64 (pingpong 반전 포함) |
| FPS | 16 |
| 길이 | 4.00초 |
| 파일 크기 | 449KB |
| 생성 시간 | 284.2초 (~4.7분) |

### GPU 환경

| 항목 | 값 |
|------|-----|
| GPU | NVIDIA GeForce RTX 5070 Ti Laptop GPU |
| VRAM | 12GB |
| 플랫폼 | WSL2 (Linux 6.6.87.2) |

---

## 4. 어댑터 구현 과정에서 발견된 추가 이슈

E2E 테스트를 위해 ComfyUI 어댑터(3파일) 외에 **기존 코드 5파일 수정**이 추가로 필요했습니다.
이는 animate 파이프라인의 CLI 실행 경로가 미완성 상태였기 때문입니다.

### 이슈 1: PipelineConfig extra="forbid"

**문제**: `PipelineConfig(extra="forbid")`가 animate 전용 키(`animate_adapters`, animate `models`)를 거부.
Hydra에서 merge된 전체 config를 `PipelineConfig`로 validate할 때 animate 키가 unknown field로 reject됨.

**수정**: `PipelineConfig`와 `AnimatePipelineConfig` 모두 `extra="ignore"`로 변경.
각 스키마가 자기 필드만 추출하고 나머지는 무시.

| 파일 | 변경 |
|------|------|
| `src/discoverex/config/schema.py` | `PipelineConfig extra="forbid"` → `"ignore"` |
| `src/discoverex/config/animate_schema.py` | `AnimatePipelineConfig extra="forbid"` → `"ignore"` |

### 이슈 2: animate 전용 config 전달 경로 부재

**문제**: `animate_pipeline` subflow가 `config.model_dump()`로 `PipelineConfig`의 dict를 전달하지만,
`PipelineConfig(extra="ignore")`가 이미 animate 전용 키를 제거한 후이므로 `AnimatePipelineConfig`에서 required field 누락 에러 발생.

**수정**: `animate_pipeline`에서 `execution_snapshot`의 `config_name`/`overrides`를 사용하여
raw Hydra config를 **재compose**하여 animate 전용 키가 포함된 원본 dict를 `build_animate_context`에 전달.

| 파일 | 변경 |
|------|------|
| `src/discoverex/flows/subflows.py` | raw config 재compose 로직 추가 |
| `src/discoverex/config_loader.py` | `load_raw_animate_config()` 함수 추가 |

### 이슈 3: 모델 포트 load() 미호출

**문제**: `build_animate_context`에서 어댑터를 instantiate한 후 `load()`를 호출하지 않음.
Dummy 어댑터는 `load()`가 no-op이라 문제 없었으나, ComfyUI 어댑터는 `load()`에서 client를 초기화.

**수정**: `build_animate_context`에서 모든 모델 포트에 대해 `load(None)` 호출 추가.

| 파일 | 변경 |
|------|------|
| `src/discoverex/bootstrap/factory.py` | load() 라이프사이클 호출 추가 |

### Hydra 설정 파일 추가

| 파일 | 내용 |
|------|------|
| `conf/animate_comfyui.yaml` | ComfyUI 어댑터 사용 최상위 config |
| `conf/flows/animate/comfyui_pipeline.yaml` | animate_pipeline flow 참조 (animate_pipeline.yaml과 동일) |

---

## 5. 검증 결과

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success: no issues found |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
| E2E (ComfyUI 연동) | **성공** — 449KB MP4, 284.2초 |

---

## 6. 전체 커밋 내역

| 커밋 | 설명 | 파일 |
|------|------|------|
| `5b61df7` | ComfyUI 어댑터 구현 | 신규 6파일 (어댑터 3 + config 1 + workflow 1 + report 1) |
| `2a9e6f6` | CLI 실행 경로 연결 | 수정 5파일 + 신규 2파일 (Hydra config) |

---

## 7. 사용 방법

```bash
# ComfyUI 서버 실행 (별도 터미널)
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# Engine에서 animate 실행
uv run discoverex animate \
  --image-path <sprite.png> \
  --config-name animate_comfyui

# 환경변수로 서버/워크플로우 경로 변경
COMFYUI_URL=http://gpu-server:8188 \
COMFYUI_WORKFLOW_PATH=conf/workflows/custom.json \
uv run discoverex animate \
  --image-path <sprite.png> \
  --config-name animate_comfyui
```

---

## 8. 남은 개선 사항

| # | 항목 | 우선순위 | 비고 |
|---|------|----------|------|
| 1 | Gemini 어댑터 연동 | HIGH | 현재 DummyVisionAnalyzer/DummyAIValidator 사용 중. Gemini 연동 시 실제 프롬프트 분석/품질 검증 가능 |
| 2 | 전체 어댑터 통합 프로필 | MEDIUM | gemini + comfyui 전체 연동 YAML 프로필 작성 |
| 3 | 생성 시간 최적화 | LOW | steps 20→15 감소, 모델 양자화 레벨 조정 등 |
| 4 | unload() 라이프사이클 | LOW | 파이프라인 종료 시 모델 포트 unload() 호출 미구현 |
