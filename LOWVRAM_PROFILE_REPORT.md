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

## 7. 모델 전체 현황

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
| **umt5-xxl-encoder-Q5_K_M.gguf** | **3.2GB** | **~2.5GB** | **저VRAM** |

---

## 8. 프로필별 예상 VRAM 비교

| 프로필 | UNet | 텍스트 인코더 | 기타 | 합계 |
|--------|------|-------------|------|------|
| `animate_comfyui` (14B) | 6.5GB | 4.5GB | 3.0GB | **~14GB** |
| `animate_comfyui` (14B Q3_K_S) | 6.5GB | 4.5GB | 3.0GB | **~14GB** |
| `animate_comfyui_lowvram` (5B) | 3.1GB | 2.5GB | 3.0GB | **~8.6GB** |
