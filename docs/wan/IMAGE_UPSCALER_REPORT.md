# 소형 이미지 자동 업스케일링 기능 구현 리포트

> 작성일: 2026-03-23
> 브랜치: wan/test

---

## 배경 및 문제

WAN I2V 모델은 **480×480** 해상도로 학습되었다. 입력 이미지가 이 크기보다 작으면 480×480 캔버스에 배치하는데, **원본이 매우 작은 경우(예: 60×83px)** 스프라이트가 캔버스의 2~3%만 차지하여 다음 문제가 발생한다:

- WAN이 모션을 제대로 생성하지 못함 (대상이 너무 작음)
- Ghosting 아티팩트 발생
- 모션 검증(수치 검증) 실패율 증가

## 해결 방식

소형 이미지를 WAN에 전달하기 전에 **자동 업스케일링**을 수행하여 캔버스 내에서 적절한 크기를 차지하도록 한다.

### 처리 흐름

```
입력 이미지 (60×83)
  → max(60, 83) = 83 < 200 (UPSCALE_THRESHOLD) → 업스케일 대상
  → Gemini Stage 1에서 art_style 판단 (예: "illustration")
  → _compute_scale_factor(60, 83, 480) = 3.76배
  → PilImageUpscaler.upscale() → Lanczos로 225×312 생성
  → 480×480 캔버스에 배치
  → WAN 모션 생성 진행
```

### 업스케일 방식 선택

| art_style | 업스케일 방식 | 이유 |
|-----------|-------------|------|
| illustration | Lanczos | 고품질 보간, 부드러운 엣지 |
| photo | Lanczos | 일반 사진에 적합 |
| vector | Lanczos | 깨끗한 엣지 보존 |
| pixel_art | Nearest-neighbor | 픽셀 경계 보존 (blur 방지) |
| unknown | Lanczos | 안전한 기본값 |

`art_style`은 기존 Gemini 모드 분류(Stage 1) 호출에 추가되어 **별도 API 호출 비용 없이** 판단된다.

### Real-ESRGAN 모델 설치

향후 고품질 업스케일이 필요할 경우를 대비하여 ComfyUI용 Real-ESRGAN 모델도 다운로드하였다.

- **경로**: `~/ComfyUI/models/upscale_models/RealESRGAN_x4plus.pth` (64MB)
- **VRAM 영향**: `finally` 블록에서 즉시 CPU로 이동하므로 WAN 생성에 VRAM 영향 없음
- **현재 미사용**: PIL Lanczos가 1차 구현, Real-ESRGAN은 동일 포트 인터페이스 뒤에 교체 가능

---

## 변경 파일

### 신규 파일 (2개)

| 파일 | 줄 수 | 내용 |
|------|------|------|
| `adapters/outbound/animate/pil_upscaler.py` | 45 | PIL Lanczos/Nearest 업스케일러 |
| `tests/test_animate_upscaler.py` | 103 | 업스케일러 + 전처리 통합 테스트 11건 |

### 수정 파일 (12개)

| 파일 | 내용 |
|------|------|
| `domain/animate.py` | `ArtStyle` enum 추가, `ModeClassification.art_style` 필드 |
| `application/ports/animate.py` | `ImageUpscalerPort` 프로토콜 추가 |
| `adapters/outbound/animate/dummy_animate.py` | `DummyImageUpscaler` 추가 |
| `application/use_cases/animate/preprocessing.py` | 업스케일 분기 + `_compute_scale_factor()` |
| `application/use_cases/animate/orchestrator.py` | `image_upscaler` 필드 + preprocess 전달 |
| `adapters/outbound/models/gemini_mode_prompt.py` | `art_style` JSON 출력 + 가이드 |
| `adapters/outbound/models/gemini_mode_classifier.py` | `art_style` 파싱 |
| `config/animate_schema.py` | `image_upscaler` 설정 항목 |
| `bootstrap/factory.py` | 업스케일러 인스턴스화 + 주입 |
| `conf/animate_comfyui.yaml` | `image_upscaler` 항목 |
| `conf/animate_comfyui_lowvram.yaml` | `image_upscaler` 항목 |
| `tests/test_animate_ports_contract.py` | `ImageUpscalerContract` 테스트 추가 |

### 문서 수정 (1개)

| 파일 | 내용 |
|------|------|
| `docs/wan/COMFYUI_FULL_SETUP.md` | 7단계 Real-ESRGAN 설치 가이드 추가 |

---

## 아키텍처

헥사고널 아키텍처 원칙을 준수하여 구현하였다.

```
Port (Protocol)
  ImageUpscalerPort.upscale(image, scale_factor, art_style) -> Path

Adapters
  ├── PilImageUpscaler     — PIL Lanczos/Nearest (기본, CPU)
  ├── DummyImageUpscaler   — 테스트용 (입력 그대로 반환)
  └── (향후) ComfyUIUpscaler — Real-ESRGAN via ComfyUI HTTP API

Config (Hydra YAML)
  animate_adapters.image_upscaler._target_ = ...PilImageUpscaler
```

### 하위 호환성

| 항목 | 보장 방식 |
|------|----------|
| `AnimateOrchestrator.image_upscaler` | 기본값 `None` → 기존 코드 변경 불필요 |
| `preprocessing.upscaler` 파라미터 | 기본값 `None` → `None`이면 업스케일 건너뜀 |
| `ModeClassification.art_style` | 기본값 `ArtStyle.UNKNOWN` |
| Gemini 응답에 `art_style` 없음 | `.get("art_style", "unknown")` 폴백 |
| 기존 YAML에 `image_upscaler` 없음 | `AnimateAdaptersConfig`에 `default_factory` 설정 |

---

## 테스트 결과

```
245 passed, 8 skipped, 0 failed (기존 234 → 245, +11 신규)
ruff check: All checks passed
200줄 제한 위반: 0건 (이번 변경 기준)
```

### 신규 테스트 (11건)

- `TestComputeScaleFactor` — 배율 계산 3건
- `TestPilImageUpscaler` — Lanczos/Nearest 업스케일 + 파일명 3건
- `TestDummyImageUpscaler` — 계약 1건
- `TestPreprocessWithUpscaler` — 전처리 통합 4건

---

## 실행 방법

기존 명령어와 100% 동일. 별도 설정 변경 불필요.

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine
cd ~/engine && export $(grep -v '^#' .env | xargs) && uv run discoverex serve --port 5001 --config-name animate_comfyui
```

- 이미지 최대 변 < 200px → **자동 업스케일** 후 WAN 진행
- 이미지 최대 변 ≥ 200px → 기존 로직 그대로 (업스케일 건너뜀)
