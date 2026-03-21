# 저VRAM 환경 모션 생성 조사 보고서

> 작성일: 2026-03-20
> 브랜치: wan/test
> 목적: 8GB 이하 VRAM GPU에서 모션 애니메이션 생성 가능 여부 조사 및 테스트

---

## 1. 목표

8GB (또는 6GB) VRAM GPU (예: RTX 3060 Laptop)에서
기존 품질을 유지하면서 모션 애니메이션 생성이 가능한 구성을 찾는 것.

---

## 2. 현재 기본 구성 (12GB GPU)

| 구성 요소 | 모델 | VRAM |
|----------|------|------|
| UNet | wan2.1-i2v-14b-480p-Q3_K_S (7.4GB) | ~7.7GB |
| 텍스트 인코더 | umt5_xxl_fp8_e4m3fn_scaled (6.3GB) | ~4.5GB |
| CLIPVision | clip_vision_h (1.2GB) | ~1.2GB |
| VAE | wan_2.1_vae (243MB) | ~0.24GB |
| **합계** | | **~12.4GB** |

프로필: `--config-name animate_comfyui`

---

## 3. 조사한 접근 방법

### 3.1 WAN 2.2 TI2V-5B — 소형 모델 교체

**결과: 품질 문제로 부적합**

| 항목 | 내용 |
|------|------|
| 모델 | Wan2.2-TI2V-5B-Q4_K_S.gguf (3.0GB) |
| 다운로드 | HuggingFace QuantStack/Wan2.2-TI2V-5B-GGUF |
| VRAM | ~3.1GB (UNet만) |

#### 발견된 문제들

**문제 1: VAE 채널 불일치**
- WAN 2.2는 48ch latent, WAN 2.1 VAE는 16ch → VAEDecode 에러
- `Wan2.2_VAE.pth` (2.7GB) 다운로드하여 해결

**문제 2: 워크플로우 노드 비호환**
- `WanImageToVideo` (WAN 2.1 전용, 16ch) → WAN 2.2에서 원본 이미지 무시
- `Wan22ImageToVideoLatent` (WAN 2.2 전용, 48ch)로 워크플로우 재구성 필요

**문제 3: CLIPVision 미지원**
- WAN 2.2 TI2V는 CLIPVision을 사용하지 않음 (VAE encode + noise_mask 방식)
- CLIPVision의 의미적 이미지 이해 없이 픽셀 수준 복원만 → 품질 저하

**문제 4: 근본적 품질 한계**
- 5B 파라미터 (14B 대비 2.8배 적음)
- 생성은 빠르지만 원본 이미지 특징 반영력 약함
- 스프라이트 애니메이션 용도에서도 눈에 띄는 품질 차이

### 3.2 GGUF 텍스트 인코더 교체

**결과: VRAM 절감 효과 없음**

| 항목 | 내용 |
|------|------|
| 모델 | umt5-xxl-encoder-Q5_K_M.gguf (3.2GB) |
| 다운로드 | HuggingFace city96/umt5-xxl-encoder-gguf |
| 예상 VRAM | ~2.5GB |
| **실측 VRAM** | **~5.1GB** |

ComfyUI-GGUF 플러그인이 텍스트 인코더를 GPU 로드 시 **FP16으로 디퀀타이즈**.
UNet은 GGUF 양자화 상태로 연산 가능하지만, 텍스트 인코더는 불가.
결과: 기존 FP8(4.5GB)보다 오히려 **더 큰 5.1GB** 사용.

### 3.3 텍스트 인코더 CPU 오프로드

**결과: 유효 — 4.5GB VRAM 절감, 속도 영향 미미**

CLIPLoader 노드의 `device` 파라미터를 `"default"` → `"cpu"`로 변경.

| 항목 | GPU (기존) | CPU 오프로드 |
|------|-----------|-------------|
| VRAM | ~4.5GB | **0GB** |
| 속도 | ~2-3초 | ~10-15초 |
| 전체 파이프라인 영향 | — | ~3-5% 추가 (무시 수준) |

텍스트 인코더는 1회만 실행되므로 CPU에서 처리해도 전체 시간에 영향 미미.

### 3.4 ComfyUI --lowvram 옵션

**결과: 테스트 진행 중**

UNet 모델을 GPU↔CPU 분할 로드하여 VRAM 부족 환경에서도 동작 가능.

```bash
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188 --lowvram
```

| 옵션 | 동작 | 속도 |
|------|------|------|
| `--normalvram` | 전체 GPU 로드 | 보통 |
| `--lowvram` | UNet 분할 GPU↔CPU 교대 | 느림 (2-3배) |
| `--novram` | 더 적극적 CPU 사용 | 매우 느림 |
| `--cpu` | 전부 CPU | 극도로 느림 |

---

## 4. 최종 프로필 구성

### 프로필 A: 기존 (12GB+)

```bash
# ComfyUI
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# Engine
uv run discoverex serve --port 5001 --config-name animate_comfyui
```

| 구성 요소 | VRAM |
|----------|------|
| UNet 14B Q3_K_S | ~7.7GB |
| 텍스트 인코더 (GPU) | ~4.5GB |
| CLIPVision + VAE | ~1.4GB |
| **합계** | **~12.4GB** |

### 프로필 B: lowvram (8-12GB)

```bash
# ComfyUI
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# Engine
uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

| 구성 요소 | VRAM |
|----------|------|
| UNet 14B Q3_K_S | ~7.7GB |
| 텍스트 인코더 (CPU) | 0GB |
| CLIPVision + VAE | ~1.4GB |
| **합계** | **~9.1GB** |

### 프로필 C: lowvram + ComfyUI --lowvram (6-8GB) — 테스트 중

```bash
# ComfyUI (UNet 분할 로드)
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188 --lowvram

# Engine
uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

| 구성 요소 | VRAM |
|----------|------|
| UNet 14B Q3_K_S (분할) | ~4-5GB |
| 텍스트 인코더 (CPU) | 0GB |
| CLIPVision + VAE | ~1.4GB |
| **합계** | **~5.5GB (예상)** |

- 품질: 14B 모델이므로 기존과 동일
- 속도: 2-3배 느림 (5-10분 예상)
- 6GB VRAM GPU 동작 가능 여부: **테스트 중**

### 프로필 D: WAN 2.2 5B (6GB 이하)

```bash
# ComfyUI
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188

# Engine
uv run discoverex serve --port 5001 --config-name animate_comfyui_wan22
```

| 구성 요소 | VRAM |
|----------|------|
| UNet 5B Q4_K_S | ~3.1GB |
| 텍스트 인코더 (CPU) | 0GB |
| WAN 2.2 VAE | ~1.3GB |
| CLIPVision 불필요 | 0GB |
| **합계** | **~5.4GB** |

- 품질: 14B 대비 낮음 (CLIPVision 미사용 + 5B 파라미터)
- 속도: 빠름
- 6GB 이하 VRAM에서만 권장

---

## 5. VRAM 시뮬레이션 테스트 방법

`--reserve-vram` 옵션으로 현재 12GB GPU에서 저VRAM 환경을 시뮬레이션:

```bash
# 8GB 시뮬레이션 (12GB 중 4GB 예약)
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188 --reserve-vram 4.0

# 6GB 시뮬레이션 (12GB 중 6GB 예약) + UNet 분할
cd ~/ComfyUI && python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 6.0
```

> 주의: VRAM만 제한되며, GPU 연산 속도는 시뮬레이션 불가.
> 실제 3060 Laptop은 CUDA 코어가 적어 생성 시간 추가 증가.

---

## 6. GPU 성능 vs VRAM

| 항목 | GPU 성능 (CUDA 코어) | VRAM |
|------|---------------------|------|
| 영향 | 생성 **속도** | 동작 **가능 여부** |
| 부족 시 | 느려짐 | **OOM 에러** (프로그램 중단) |
| 품질 영향 | 없음 | 없음 |

- **OOM (Out Of Memory)**: GPU 메모리 부족으로 프로그램이 중단되는 에러
- `--lowvram` 옵션으로 VRAM 부족 시 CPU RAM을 대신 사용 가능 (속도 저하)

---

## 7. 다운로드된 모델 현황

### 사용 중

| 파일 | 크기 | 위치 | 용도 |
|------|------|------|------|
| wan2.1-i2v-14b-480p-Q3_K_S.gguf | 7.4GB | ~/ComfyUI/models/unet/ | 기본 모델 |
| wan2.1-i2v-14b-480p-Q4_K_S.gguf | 9.8GB | ~/ComfyUI/models/unet/ | 고품질 |
| wan2.1-i2v-14b-480p-Q4_K_M.gguf | 11GB | ~/ComfyUI/models/unet/ | 최고품질 |
| umt5_xxl_fp8_e4m3fn_scaled.safetensors | 6.3GB | ~/ComfyUI/models/clip/ | 텍스트 인코더 |
| clip_vision_h.safetensors | 1.2GB | ~/ComfyUI/models/clip_vision/ | CLIP Vision |
| wan_2.1_vae.safetensors | 243MB | ~/ComfyUI/models/vae/ | VAE |

### WAN 2.2 관련 (테스트용, 품질 부적합)

| 파일 | 크기 | 위치 | 비고 |
|------|------|------|------|
| Wan2.2-TI2V-5B-Q4_K_S.gguf | 3.0GB | ~/ComfyUI/models/unet/ | 5B 모델 |
| Wan2.2_VAE.pth | 2.7GB | ~/ComfyUI/models/vae/ | 48ch VAE |
| umt5-xxl-encoder-Q5_K_M.gguf | 3.2GB | ~/ComfyUI/models/clip/ | GGUF 텍스트 인코더 (효과 없음) |

---

## 8. 결론

| 환경 | 추천 프로필 | 품질 | 속도 |
|------|-----------|------|------|
| 12GB+ GPU | 프로필 A (`animate_comfyui`) | 최고 | 보통 |
| 8-12GB GPU | 프로필 B (`animate_comfyui_lowvram`) | 최고 | 보통 |
| 6-8GB GPU | **프로필 C** (lowvram + `--lowvram`) | **최고** | **느림** |
| 6GB 이하 | 프로필 D (`animate_comfyui_wan22`) | 낮음 | 빠름 |

**프로필 C (14B + 텍스트 인코더 CPU + ComfyUI --lowvram)가 6GB GPU에서
품질 유지 가능한 최선의 조합. 현재 테스트 진행 중.**
