# WAN 2.2 TI2V-5B 프로필 추가 보고서

> 작성일: 2026-03-20
> 브랜치: wan/test
> 목적: 8GB 이하 VRAM 환경에서 모션 생성을 위한 WAN 2.2 5B 프로필 추가

---

## 1. 배경

### 목표

8GB VRAM GPU에서 모션 애니메이션 생성이 가능하도록 경량 프로필 추가.

### 기존 프로필 한계

| 프로필 | 모델 | VRAM | 8GB 가능 |
|--------|------|------|----------|
| `animate_comfyui` | WAN 2.1 14B | ~12GB | ❌ |
| `animate_comfyui_lowvram` | WAN 2.1 14B + CPU 오프로드 | ~8GB | ⚠️ 여유 없음 |

WAN 2.1 14B는 모델 자체가 7.7GB를 차지하여 8GB GPU에서 OOM 위험.

---

## 2. WAN 2.2 TI2V-5B 도입 과정에서 발견된 이슈

### 이슈 1: VAE 채널 불일치 (해결)

WAN 2.2는 48ch latent를 사용하여 WAN 2.1 VAE(16ch)와 호환 불가.

```
RuntimeError: expected input to have 16 channels, but got 48 channels
```

→ `Wan2.2_VAE.pth` (48ch, 2.7GB) 다운로드하여 해결.

### 이슈 2: 원본 이미지 무시 — 노드 비호환 (해결)

`WanImageToVideo` 노드는 WAN 2.1 전용 (16ch latent + CLIPVision 이미지 조건).
WAN 2.2 모델에 사용하면 이미지 조건이 무시되어 원본과 무관한 영상 생성.

| 노드 | latent | 이미지 조건 방식 | 대상 |
|------|--------|----------------|------|
| `WanImageToVideo` | 16ch, /8 downsample | CLIPVision + VAE concat | WAN 2.1 전용 |
| `Wan22ImageToVideoLatent` | 48ch, /16 downsample | VAE encode + noise_mask | WAN 2.2 전용 |

→ WAN 2.2 전용 워크플로우를 `Wan22ImageToVideoLatent` 노드로 새로 구성.

### 이슈 3: GGUF 텍스트 인코더 VRAM 절감 효과 없음 (확인)

GGUF 텍스트 인코더(`umt5-xxl-encoder-Q5_K_M.gguf`)가 GPU 로드 시 FP16으로
디퀀타이즈되어 5.1GB 사용 → 기존 FP8(4.5GB)보다 오히려 큼.

→ 텍스트 인코더는 GGUF가 아닌 **CPU 오프로드**가 유효한 방법.

---

## 3. 최종 구성 — WAN 2.2 워크플로우

### 노드 구조 (API 포맷)

```
CLIPLoader (node 2, device=cpu)
  → CLIPTextEncode positive (node 5) → KSampler (node 10)
  → CLIPTextEncode negative (node 6) → KSampler (node 10)

VAELoader (node 3, Wan2.2_VAE.pth)
  → Wan22ImageToVideoLatent (node 9)
  → VAEDecode (node 11)

LoadImage (node 7)
  → Wan22ImageToVideoLatent (node 9, start_image)

Wan22ImageToVideoLatent (node 9)
  → KSampler (node 10, latent_image)

UnetLoaderGGUF (node 16, Wan2.2-TI2V-5B-Q4_K_S.gguf)
  → KSampler (node 10, model)

KSampler (node 10) → VAEDecode (node 11) → VHS_VideoCombine (node 12)
```

### WAN 2.1 대비 차이

| 항목 | WAN 2.1 워크플로우 | WAN 2.2 워크플로우 |
|------|-------------------|-------------------|
| 이미지→영상 노드 | `WanImageToVideo` | `Wan22ImageToVideoLatent` |
| CLIPVision 사용 | ✅ (CLIPVisionLoader + CLIPVisionEncode) | ❌ (불필요) |
| 이미지 조건 방식 | CLIPVision embedding + VAE concat | VAE encode + noise_mask |
| conditioning 출력 | positive/negative/latent 3개 | latent 1개 |
| positive/negative 연결 | 노드 경유 | KSampler 직접 연결 |
| latent 채널 | 16ch | 48ch |
| downsample | /8 | /16 |

---

## 4. 예상 VRAM (WAN 2.2 프로필)

| 구성 요소 | VRAM |
|----------|------|
| WAN22 5B Q4_K_S | ~3.1GB |
| 텍스트 인코더 (CPU 오프로드) | 0GB |
| WAN 2.2 VAE | ~1.3GB |
| CLIPVision | 불필요 (0GB) |
| 동적 할당 | ~1.0GB |
| **합계** | **~5.4GB** |

---

## 5. 변경 파일

### 신규 파일 (기존 파일 변경 없음)

| 파일 | 내용 |
|------|------|
| `conf/workflows/wan22_ti2v_lowvram.json` | WAN 2.2 전용 API 워크플로우 (CLIPVision 제거, Wan22ImageToVideoLatent) |
| `conf/animate_comfyui_wan22.yaml` | WAN 2.2 전용 Hydra 프로필 |

### 수정 파일 (추가만, 기존 로직 변경 없음)

| 파일 | 변경 | 기존 영향 |
|------|------|----------|
| `comfyui_workflow.py` | `_WIDGET_KEYS`에 `Wan22ImageToVideoLatent` 1줄 추가 | ❌ 없음 |
| `comfyui_workflow.py` | inject 루프에 `Wan22ImageToVideoLatent` 분기 추가 | ❌ 없음 |

### 변경 없음 확인

| 파일 | 상태 |
|------|------|
| `conf/workflows/wan21_i2v.json` | ❌ 변경 없음 |
| `conf/workflows/wan21_i2v_lowvram.json` | ❌ 변경 없음 |
| `conf/animate_comfyui.yaml` | ❌ 변경 없음 |
| `conf/animate_comfyui_lowvram.yaml` | ❌ 변경 없음 |
| `comfyui_wan_generator.py` | ❌ 변경 없음 |
| `comfyui_client.py` | ❌ 변경 없음 |

---

## 6. 전체 프로필 비교

| 프로필 | 명령 | 모델 | VRAM | 용도 |
|--------|------|------|------|------|
| 기존 | `--config-name animate_comfyui` | WAN 2.1 14B | ~12GB | 고품질 |
| lowvram | `--config-name animate_comfyui_lowvram` | WAN 2.1 14B + CPU오프로드 | ~8GB | 12GB GPU |
| **wan22** | `--config-name animate_comfyui_wan22` | **WAN 2.2 5B + CPU오프로드** | **~5.4GB** | **8GB GPU** |

### 실행 방법

```bash
# 기존 (변경 없음)
uv run discoverex serve --port 5001 --config-name animate_comfyui

# WAN 2.1 lowvram (변경 없음)
uv run discoverex serve --port 5001 --config-name animate_comfyui_lowvram

# WAN 2.2 5B (신규)
uv run discoverex serve --port 5001 --config-name animate_comfyui_wan22
```

---

## 7. 품질 비교 예상

| 항목 | WAN 2.1 14B Q3_K_S | WAN 2.2 5B Q4_K_S |
|------|-------------------|-------------------|
| 파라미터 | 14B | 5B (2.8배 적음) |
| 양자화 | Q3_K_S (공격적) | Q4_K_S (보통) |
| 세대 | 2.1 | 2.2 (신형) |
| 학습 해상도 | 480p | 720p |
| 디테일 | 높음 | 보통 |
| 복잡한 모션 | 우수 | 열세 가능 |

스프라이트 애니메이션(480x480, 단순 모션) 용도에서는 차이가 크지 않을 수 있음.
실제 동일 이미지로 비교 생성하여 품질 확인 필요.

---

## 8. 다운로드된 모델

| 파일 | 크기 | 위치 |
|------|------|------|
| `Wan2.2-TI2V-5B-Q4_K_S.gguf` | 3.0GB | `~/ComfyUI/models/unet/` |
| `Wan2.2_VAE.pth` | 2.7GB | `~/ComfyUI/models/vae/` |
| `umt5-xxl-encoder-Q5_K_M.gguf` | 3.2GB | `~/ComfyUI/models/clip/` (VRAM 절감 효과 없어 미사용) |
