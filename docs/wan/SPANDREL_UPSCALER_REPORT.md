# Real-ESRGAN AI 초해상도 업스케일러 구현 리포트

> 작성일: 2026-03-23
> 커밋: 9618aa1
> 브랜치: wan/test

---

## 배경

이전 커밋(`d21d8a6`)에서 소형 이미지 자동 업스케일링 기능을 구현하였으나, PIL Lanczos 보간만 사용하여 **크기만 커질 뿐 디테일은 개선되지 않는 문제**가 확인되었다.

### PIL Lanczos vs Real-ESRGAN

| 방식 | 원리 | 결과 |
|------|------|------|
| PIL Lanczos (이전) | 수학적 보간 — 주변 픽셀 가중 평균 | 크기만 커짐, 뿌옇게 |
| Real-ESRGAN (현재) | 신경망이 디테일을 **생성** | 선명한 엣지, 텍스처 복원 |

## 구현 내용

### SpandrelUpscaler 어댑터

`spandrel` 라이브러리를 사용하여 ComfyUI HTTP API 없이 **Engine 프로세스에서 직접** Real-ESRGAN을 실행한다.

```
ImageUpscalerPort (동일 인터페이스)
  ├── PilImageUpscaler      ← 이전 (보간만, 폴백용으로 유지)
  ├── SpandrelUpscaler      ← 현재 기본값 (AI 초해상도) ★
  └── DummyImageUpscaler    ← 테스트용
```

### 핵심 동작

```python
# spandrel로 Real-ESRGAN 모델 로드
model = spandrel.ModelLoader().load_from_file("RealESRGAN_x4plus.pth")

# GPU에서 AI 추론 → 4x 업스케일 (디테일 생성)
model.to("cuda")
output = model(input_tensor)  # 60x83 → 240x332

# 즉시 GPU 반환
model.to("cpu")
torch.cuda.empty_cache()
```

### 주요 특징

| 항목 | 내용 |
|------|------|
| 모델 | RealESRGAN_x4plus.pth (64MB, ESRGAN 아키텍처) |
| 스케일 | 4x 고정 (요청 배율이 다르면 추가 Lanczos 리사이즈) |
| 타일 처리 | 512×512 타일 + 32px 겹침 → 큰 이미지도 OOM 없이 처리 |
| pixel_art | nearest-neighbor 유지 (AI 업스케일 대신) |
| VRAM | ~200MB (소형 이미지 기준), 사용 후 즉시 반환 |
| WAN 영향 | 없음 — 전처리 단계에서 실행 후 해제, WAN 로드 전 VRAM 비움 |

### GPU 테스트 결과

```
입력: (60, 83) -> 출력: (240, 332)
스케일: 4x
GPU 사용: cuda
SUCCESS
```

## 변경 파일

### 신규 파일 (1개)

| 파일 | 줄 수 | 내용 |
|------|------|------|
| `adapters/outbound/animate/spandrel_upscaler.py` | 137 | Spandrel 기반 AI 업스케일러 |

### 수정 파일 (4개)

| 파일 | 내용 |
|------|------|
| `pyproject.toml` | `animate` extra에 `spandrel>=0.4.0`, `torch>=2.10.0` 추가 |
| `config/animate_schema.py` | 기본값을 `SpandrelUpscaler`로 변경 |
| `conf/animate_comfyui.yaml` | `image_upscaler` → SpandrelUpscaler + model_path/device 설정 |
| `conf/animate_comfyui_lowvram.yaml` | 동일 |

## VRAM 타임라인

```
시간 →

[ESRGAN 로드]    ██░░░░░░░░░░░░░░░░  (~64MB + 작업 메모리)
[AI 업스케일]    ████░░░░░░░░░░░░░░  (타일 추론)
[ESRGAN 해제]    ░░░░░░░░░░░░░░░░░░  (CPU 이동 + cache 클리어)
[WAN 모델 로드]  ░░░░░░████████████  (~8-10GB, ESRGAN과 겹치지 않음)
```

## 실행 방법

기존과 동일. 별도 설정 변경 불필요.

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188

# 터미널 2: Engine
cd ~/engine && export $(grep -v '^#' .env | xargs) && uv run discoverex serve --port 5001 --config-name animate_comfyui
```

## 버그 수정: RGBA 투명 배경 → 검은 박스 문제 (f1d2446)

### 증상

투명 배경(RGBA)의 소형 이미지를 업스케일하면 투명 영역이 **검은색 박스**로 변환되어 WAN에 전달됨. WAN이 검은 배경 위에서 모션을 생성하여 결과물에 검은 영역이 포함됨.

### 원인

```
원본 (60×83, RGBA, 투명 배경 44.5%)
  → convert("RGB")  ← PIL이 투명 픽셀을 검은색(0,0,0)으로 변환 ★
  → Real-ESRGAN 추론 → 검은 배경 포함 업스케일
  → white_anchor → 배경 평균 < 200 (검은색) → 미적용
  → WAN → 검은 배경 그대로 모션 생성
```

### 수정

`spandrel_upscaler.py`에서 RGBA 이미지의 투명 영역을 **흰색으로 합성** 후 RGB 변환:

```python
if raw.mode == "RGBA":
    bg = Image.new("RGB", raw.size, (255, 255, 255))
    bg.paste(raw, mask=raw.split()[3])  # 알파 채널을 마스크로 사용
    src = bg
```

### 결과

- 검은색 픽셀: 16.0% → **0%**
- white_anchor 정상 작동 (배경 평균 > 200)
- WAN 흰색 배경 위에서 정상 모션 생성

---

## 폴백

GPU/spandrel이 없는 환경에서는 YAML에서 `PilImageUpscaler`로 전환 가능:

```yaml
image_upscaler:
  _target_: discoverex.adapters.outbound.animate.pil_upscaler.PilImageUpscaler
```
