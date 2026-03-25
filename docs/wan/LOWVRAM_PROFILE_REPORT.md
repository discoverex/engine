# 저VRAM 프로필 추가 보고서

> 작성일: 2026-03-20
> 브랜치: wan/test
> 목적: 6GB VRAM 환경에서 모션 생성 가능하도록 별도 프로필 추가

---

## 1. 문제

WAN 2.2 TI2V-5B Q4_K_S 모델(3.0GB)로 교체해도 VRAM 사용량이 ~9.7GB로
14B 모델과 비슷한 수준이었음.

### 원인: 텍스트 인코더가 고정 비용

| 구성 요소 | 파일 | VRAM |
|----------|------|------|
| TI2V-5B Q4_K_S | `Wan2.2-TI2V-5B-Q4_K_S.gguf` | ~3.1GB |
| **텍스트 인코더 (주범)** | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` (6.3GB) | **~4.5GB** |
| CLIP Vision | `clip_vision_h.safetensors` | ~1.0GB |
| VAE | `wan_2.1_vae.safetensors` | ~0.5GB |
| 동적 할당 | latent, attention 텐서 | ~1.5GB |
| **합계** | | **~9.6GB** |

모델을 아무리 작게 양자화해도 텍스트 인코더(UMT5-XXL FP8)가 4.5GB로 고정.

---

## 2. 해결 방법

텍스트 인코더도 GGUF 양자화 버전으로 교체.

| 항목 | 기존 (safetensors) | GGUF (Q5_K_M) |
|------|-------------------|---------------|
| 파일 | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `umt5-xxl-encoder-Q5_K_M.gguf` |
| 파일 크기 | 6.3GB | 3.2GB |
| VRAM | ~4.5GB | ~2.5GB |
| ComfyUI 노드 | `CLIPLoader` | `CLIPLoaderGGUF` |

### 예상 VRAM (최적화 후)

| 구성 요소 | VRAM |
|----------|------|
| TI2V-5B Q4_K_S | ~3.1GB |
| 텍스트 인코더 GGUF Q5_K_M | ~2.5GB |
| CLIP Vision + VAE | ~1.5GB |
| 동적 할당 | ~1.5GB |
| **합계** | **~8.6GB** |

기존 ~9.6GB → **~8.6GB** (약 1GB 절감).

---

## 3. 구현 — 기존 코드 변경 없이 신규 파일만 추가

### 설계 원칙

- 기존 워크플로우(`wan21_i2v.json`) 변경 없음
- 기존 설정(`animate_comfyui.yaml`) 변경 없음
- 기존 코드 로직 변경 최소화 (1줄 추가만)
- 별도 프로필로 분리하여 `--config-name` 옵션으로 전환

### 변경 파일

| 파일 | 유형 | 변경 | 기존 영향 |
|------|------|------|----------|
| `comfyui_workflow.py` | 수정 | `_WIDGET_KEYS`에 `CLIPLoaderGGUF` 1줄 추가 | ❌ 없음 (기존 `CLIPLoader` 그대로) |

### 신규 파일

| 파일 | 내용 |
|------|------|
| `conf/workflows/wan22_i2v_lowvram.json` | CLIPLoaderGGUF + 5B 모델 워크플로우 |
| `conf/models/animation_generation/comfyui_lowvram.yaml` | lowvram 워크플로우 Hydra 설정 |
| `conf/animate_comfyui_lowvram.yaml` | lowvram 전체 프로필 (Gemini + ComfyUI + 실제 어댑터) |

### 다운로드된 모델

| 파일 | 크기 | 위치 |
|------|------|------|
| `Wan2.2-TI2V-5B-Q4_K_S.gguf` | 3.0GB | `~/ComfyUI/models/unet/` |
| `umt5-xxl-encoder-Q5_K_M.gguf` | 3.2GB | `~/ComfyUI/models/clip/` |

---

## 4. 워크플로우 비교

### 기존: `wan21_i2v.json`

```
CLIPLoader (node 2)
  → umt5_xxl_fp8_e4m3fn_scaled.safetensors (FP8, 6.3GB)
  → type: "wan"

UnetLoaderGGUF (node 16)
  → wan2.1-i2v-14b-480p-Q3_K_S.gguf (7.4GB)
```

### 신규: `wan22_i2v_lowvram.json`

```
CLIPLoaderGGUF (node 2)           ← 노드 타입 변경
  → umt5-xxl-encoder-Q5_K_M.gguf (GGUF, 3.2GB)
  → type: "wan"

UnetLoaderGGUF (node 16)
  → Wan2.2-TI2V-5B-Q4_K_S.gguf (3.0GB)  ← 모델 변경
```

나머지 노드(CLIPVisionLoader, VAELoader, KSampler, WanImageToVideo, VHS_VideoCombine 등)는 동일.

---

## 5. comfyui_workflow.py 변경 상세

```python
# 기존 (변경 없음)
"CLIPLoader": ["clip_name", "type", "device"],

# 추가 (1줄)
"CLIPLoaderGGUF": ["clip_name", "type"],
```

`CLIPLoaderGGUF`는 `device` 위젯이 없으므로 `["clip_name", "type"]`만 매핑.
기존 워크플로우에는 `CLIPLoaderGGUF` 노드가 없으므로 이 매핑이 사용되지 않음 → 기존 동작 영향 0.

---

## 6. 실행 방법

```bash
# 기존 프로필 (14B, 고VRAM) — 변경 없음
uv run discoverex serve --port 5001 --config-name animate_comfyui

# 저VRAM 프로필 (5B + GGUF CLIP) — 신규
uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram
```

대시보드에서 모델 선택 UI는 동일하게 동작. 워크플로우에 지정된 기본 모델이
`Wan2.2-TI2V-5B-Q4_K_S.gguf`이며, 대시보드에서 다른 모델로 전환도 가능.

---

## 7. VAE 채널 불일치 수정 (48ch 문제)

### 증상

lowvram 프로필로 첫 실행 시 VAEDecode에서 에러 발생:

```
RuntimeError: Given groups=1, weight of size [16, 16, 1, 1, 1],
expected input[1, 48, 9, 60, 60] to have 16 channels, but got 48 channels instead
```

### 원인

WAN 2.1과 WAN 2.2는 **latent space 채널 수가 다름**:

| 항목 | WAN 2.1 | WAN 2.2 |
|------|---------|---------|
| latent 채널 | 16 channels | **48 channels** |
| VAE | `wan_2.1_vae.safetensors` (243MB) | `Wan2.2_VAE.pth` (2.7GB) |

초기 lowvram 워크플로우에서 WAN 2.1 VAE를 그대로 사용하여,
WAN 2.2 모델이 생성한 48ch latent를 16ch VAE가 디코딩하려다 실패.

### 수정

`wan22_i2v_lowvram.json`의 VAELoader 노드를 WAN 2.2 전용 VAE로 교체:

```
VAELoader (node 3):
  수정 전: wan_2.1_vae.safetensors (16ch, 243MB)
  수정 후: Wan2.2_VAE.pth (48ch, 2.7GB)
```

### 다운로드

```
소스: https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B/resolve/main/Wan2.2_VAE.pth
위치: ~/ComfyUI/models/vae/Wan2.2_VAE.pth (2.7GB)
```

### 기존 영향

| 파일 | 영향 |
|------|------|
| `wan21_i2v.json` (기존 워크플로우) | ❌ 변경 없음 — `wan_2.1_vae.safetensors` 그대로 |
| `wan22_i2v_lowvram.json` | ✅ VAE 교체 |

---

## 8. 모델 전체 현황

### UNet (diffusion) 모델

| 모델 | 크기 | VRAM | 용도 |
|------|------|------|------|
| wan2.1-i2v-14b-480p-Q3_K_S | 7.4GB | ~6.5GB | 기존 기본 |
| wan2.1-i2v-14b-480p-Q4_K_S | 9.8GB | ~8.75GB | 고품질 |
| wan2.1-i2v-14b-480p-Q4_K_M | 11GB | ~9.65GB | 최고품질 |
| **Wan2.2-TI2V-5B-Q4_K_S** | **3.0GB** | **~3.1GB** | **저VRAM** |

### 텍스트 인코더

| 모델 | 크기 | VRAM | 용도 |
|------|------|------|------|
| umt5_xxl_fp8_e4m3fn_scaled.safetensors | 6.3GB | ~4.5GB | 기존 기본 |
| **umt5-xxl-encoder-Q5_K_M.gguf** | **3.2GB** | **~5.1GB (FP16 디퀀타이즈)** | **저VRAM (주의사항 참조)** |

### VAE

| 모델 | 크기 | latent 채널 | 용도 |
|------|------|------------|------|
| wan_2.1_vae.safetensors | 243MB | 16ch | WAN 2.1 전용 |
| **Wan2.2_VAE.pth** | **2.7GB** | **48ch** | **WAN 2.2 전용** |

---

## 9. GGUF 텍스트 인코더 VRAM 주의사항

### 실측 결과

GGUF 텍스트 인코더가 예상보다 VRAM을 많이 사용:

| 항목 | 예상 | 실측 | 원인 |
|------|------|------|------|
| umt5-xxl Q5_K_M GGUF | ~2.5GB | **~5.1GB** | GPU 로드 시 FP16으로 디퀀타이즈 |

ComfyUI-GGUF 플러그인은 UNet은 양자화 상태로 GPU 연산이 가능하지만,
텍스트 인코더는 **FP16으로 풀어서 로드**하는 구현 한계가 있음.
결과적으로 FP8 safetensors(4.5GB)보다 오히려 **더 큰 5.1GB** 사용.

### 실측 VRAM 사용 내역 (lowvram 프로필)

| 구성 요소 | VRAM |
|----------|------|
| CLIPVision | 1,208MB |
| 텍스트 인코더 (GGUF → FP16) | 5,129MB |
| VAE (WAN 2.2) | 242MB |
| WAN22 5B Q4_K | 3,055MB |
| **합계** | **~9.6GB** |

### 추가 최적화 방향

텍스트 인코더를 CPU 오프로드하면 VRAM ~6GB로 감소 가능:

| 구성 요소 | CPU 오프로드 시 |
|----------|---------------|
| CLIPVision | 1,208MB |
| 텍스트 인코더 | **0MB** (CPU) |
| VAE (WAN 2.2) | 242MB |
| WAN22 5B Q4_K | 3,055MB |
| **합계** | **~4.5GB** |

이는 CLIPLoader(GGUF)의 `device` 파라미터를 `cpu`로 설정하여 구현 가능.
현재는 미적용 상태이며, 필요 시 워크플로우에 반영 가능.

---

## 10. 프로필별 VRAM 비교 (실측 반영)

| 프로필 | UNet | 텍스트 인코더 | VAE | CLIP Vision | 합계 |
|--------|------|-------------|-----|-------------|------|
| `animate_comfyui` (14B Q3_K_S) | 6.5GB | 4.5GB (FP8) | 0.24GB | 1.2GB | **~12.4GB** |
| `animate_comfyui_lowvram` (5B) | 3.1GB | 5.1GB (GGUF→FP16) | 0.24GB | 1.2GB | **~9.6GB** |
| lowvram + CPU 오프로드 (미적용) | 3.1GB | 0GB (CPU) | 0.24GB | 1.2GB | **~4.5GB** |
