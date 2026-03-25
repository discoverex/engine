# ComfyUI 어댑터 구현 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 대상: AnimationGenerationPort의 ComfyUI 구현체 — engine에서 실제 WAN I2V 모션 생성 가능하게 함

---

## 1. 배경

Engine의 animate 파이프라인은 골격(포트/유스케이스/Gemini 어댑터)이 완성되었으나,
`AnimationGenerationPort`의 실제 구현체가 없어 `DummyAnimationGenerator`(19바이트 더미 MP4)만 반환하는 상태였음.

실제 모션 생성을 위해 sprite_gen의 `wan_backend.py`에 있는 `ComfyUIClient` + `load_workflow_from_file`을
engine의 헥사고널 아키텍처(포트/어댑터 패턴)에 맞게 포팅.

---

## 2. 구현 구조

sprite_gen의 단일 파일(2,602줄) 중 ComfyUI 관련 핵심 로직(~350줄)을 추출하여
engine의 200줄 제약에 맞게 3파일로 분리.

### 파일 구성

| 파일 | 줄수 | 책임 |
|------|------|------|
| `comfyui_client.py` | 180 | ComfyUI HTTP API 전송 계층 (순수 HTTP, 도메인 무관) |
| `comfyui_workflow.py` | 141 | 워크플로우 JSON 로드 + GUI→API 변환 + 파라미터 주입 |
| `comfyui_wan_generator.py` | 125 | `AnimationGenerationPort` 구현체 (라이프사이클 오케스트레이션) |
| **합계** | **446** | |

### 설정 파일

| 파일 | 내용 |
|------|------|
| `conf/models/animation_generation/comfyui.yaml` | Hydra 설정 (`_target_`, 서버 URL, 워크플로우 경로, 타임아웃) |
| `conf/workflows/wan21_i2v.json` | ComfyUI 워크플로우 템플릿 (sprite_gen에서 복사) |

---

## 3. 아키텍처 설계

### 3.1 계층 분리

```
AnimationGenerationPort (Protocol)
        ↑ implements
ComfyUIWanGenerator (어댑터)
    ├── ComfyUIClient (HTTP 전송)
    └── load_and_inject() (워크플로우 주입)
```

- **ComfyUIClient**: urllib.request만 사용하는 순수 HTTP 클라이언트. 도메인 지식 없음.
- **comfyui_workflow**: 워크플로우 JSON 로드 + 파라미터 주입 순수 함수. 부수효과 없음.
- **ComfyUIWanGenerator**: 포트 구현체. load/generate/unload 라이프사이클 오케스트레이션.

### 3.2 포트 인터페이스 매핑

```python
class AnimationGenerationPort(Protocol):
    def load(self, handle: ModelHandle) -> None: ...
    def generate(self, handle, uploaded_image, params) -> AnimationResult: ...
    def unload(self) -> None: ...
```

| 메서드 | ComfyUIWanGenerator 구현 |
|--------|-------------------------|
| `load()` | ComfyUIClient 인스턴스 생성, health_check, 워크플로우 파일 존재 확인 |
| `generate()` | 이미지 업로드 → 워크플로우 주입 → 큐 제출 → 폴링 대기 → 비디오 다운로드 |
| `unload()` | ComfyUI VRAM/RAM 해제 (`/free` API + gc.collect) |

### 3.3 generate() 실행 흐름

```
1. upload_image(image_path)     → POST /upload/image → uploaded_filename
2. load_and_inject(workflow)    → 워크플로우 JSON에 파라미터 주입
3. queue_prompt(workflow)       → POST /prompt → prompt_id
4. wait_for_completion(id)      → GET /history/{id} 폴링 (2초 간격, 30분 타임아웃)
5. download_video(history)      → GET /view?filename=...&type=output → MP4 저장
6. (선택) free_memory()         → POST /free (free_between_attempts=true 시)
7. return AnimationResult(video_path, seed, attempt)
```

---

## 4. sprite_gen 대비 변경점

### 유지

- ComfyUI REST API 5개 엔드포인트 (upload, prompt, history, view, free)
- GUI→API 워크플로우 자동 변환 (`_gui_to_api`)
- 파라미터 주입 로직 (CLIPTextEncode, KSampler, VHS_VideoCombine, LoadImage, WanImageToVideo)
- `gc.collect()` + `torch.cuda.empty_cache()` 메모리 정리

### 제거

| 항목 | 사유 |
|------|------|
| 콘솔 프로그레스 바 (unicode 블록/스피너) | `logger.info`로 대체 (30초 간격 로깅) |
| `_get_vram_usage` / `_get_ram_usage` | subprocess nvidia-smi/free 호출은 어댑터 범위 밖 |
| VRAM/RAM 델타 로깅 | 위와 동일 |
| `_apply_post_compositing` | engine의 별도 파이프라인 단계에서 처리 |
| 환경변수 직접 참조 | Hydra `oc.env` resolver로 대체 |

### 개선

| 항목 | 내용 |
|------|------|
| 설정 주입 | 글로벌 상수 → Hydra YAML 설정 (`base_url`, `workflow_path`, 타임아웃 등) |
| 에러 처리 | `load()`에서 fail-fast (health_check, 워크플로우 파일 확인) |
| 타이머 | `time.time()` → `time.monotonic()` (시계 보정 영향 없음) |

---

## 5. Hydra 설정

### comfyui.yaml

```yaml
_target_: discoverex.adapters.outbound.models.comfyui_wan_generator.ComfyUIWanGenerator
base_url: ${oc.env:COMFYUI_URL,http://127.0.0.1:8188}
workflow_path: ${oc.env:COMFYUI_WORKFLOW_PATH,conf/workflows/wan21_i2v.json}
steps: 20
width: 480
height: 480
timeout_upload: 30
timeout_poll: 1800
poll_interval: 2.0
free_between_attempts: false
```

### 어댑터 전환 방법

```bash
# Dummy → ComfyUI 전환 (런타임 오버라이드)
discoverex animate --image-path <sprite.png> \
  -o models/animation_generation=comfyui

# 환경변수로 서버 URL 변경
COMFYUI_URL=http://gpu-server:8188 \
discoverex animate --image-path <sprite.png> \
  -o models/animation_generation=comfyui
```

기존 코드(bootstrap/factory.py, retry_loop.py, orchestrator.py, CLI) 변경 없음.
Hydra `_target_`이 어댑터 클래스를 직접 지정하므로 YAML 전환만으로 동작.

---

## 6. 검증 결과

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed (3 new files) |
| mypy strict | Success: no issues found in 3 source files |
| 200줄 제약 | 0건 위반 (180 / 141 / 125) |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |

---

## 7. 실제 모션 생성까지 남은 단계

### 완료된 항목

- [x] AnimationGenerationPort ComfyUI 어댑터 구현 (이번 작업)
- [x] Hydra 설정 + 워크플로우 파일
- [x] CLI `--image-path` 인자 (이미 구현되어 있었음)

### 남은 항목

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 1 | ComfyUI 서버 실행 | **인프라 준비 필요** | `http://127.0.0.1:8188` |
| 2 | WAN 2.1 모델 파일 | **인프라 준비 필요** | `wan2.1-i2v-14b-480p-Q3_K_S.gguf` |
| 3 | CLIP/VAE 모델 | **인프라 준비 필요** | `clip_vision_h.safetensors`, `wan_2.1_vae.safetensors` |
| 4 | Gemini API 키 | **인프라 준비 필요** | Vision/AI/PostMotion 어댑터용 |
| 5 | Hydra 설정 전환 | **설정 작업 필요** | 전체 모델을 gemini/comfyui로 전환하는 프로필 YAML |
| 6 | E2E 테스트 | **테스트 필요** | ComfyUI 서버 연동 통합 테스트 |

---

## 8. 파일 변경 요약

### 신규 파일

| 파일 | 경로 |
|------|------|
| ComfyUI HTTP 클라이언트 | `src/discoverex/adapters/outbound/models/comfyui_client.py` |
| 워크플로우 로더 | `src/discoverex/adapters/outbound/models/comfyui_workflow.py` |
| AnimationGenerationPort 어댑터 | `src/discoverex/adapters/outbound/models/comfyui_wan_generator.py` |
| Hydra 설정 | `conf/models/animation_generation/comfyui.yaml` |
| 워크플로우 템플릿 | `conf/workflows/wan21_i2v.json` |

### 수정된 기존 파일

없음.
