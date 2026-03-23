# WAN I2V 모델 순차 로드/해제 VRAM 최적화 분석

> 작성일: 2026-03-23
> 상태: 분석 완료, 구현 미진행 (추후 검토)

---

## 배경

WAN I2V 파이프라인은 4개 모델을 사용한다. 현재 ComfyUI는 이 4개 모델을 **동시에 VRAM에 로드**하여 피크 ~13.7GB를 사용한다. 모델을 순차적으로 로드/해제하면 VRAM 사용량을 줄일 수 있는지 분석하였다.

## 4개 모델 및 VRAM 사용량

| 모델 | 파일 | 용도 | VRAM |
|------|------|------|------|
| CLIP Text | umt5_xxl_fp8_e4m3fn_scaled.safetensors | 텍스트 프롬프트 인코딩 | ~4.5GB |
| CLIP Vision | clip_vision_h.safetensors | 입력 이미지 인코딩 | ~1.2GB |
| UNet | wan2.1-i2v-14b-480p-Q3_K_S.gguf | 디퓨전 샘플링 (핵심) | ~7.7GB |
| VAE | wan_2.1_vae.safetensors | 잠재 공간 ↔ 이미지 디코딩 | ~0.3GB |

## 실행 순서 및 모델 사용 시점

| 순서 | 노드 | 사용 모델 | 설명 |
|------|------|----------|------|
| 1 | CLIPTextEncode (positive) | CLIP Text | 텍스트 프롬프트 인코딩 |
| 2 | CLIPTextEncode (negative) | CLIP Text | 네거티브 프롬프트 인코딩 |
| 3 | CLIPVisionEncode | CLIP Vision | 입력 이미지 인코딩 |
| 4 | WanImageToVideo | VAE | 시작 이미지 잠재 공간 인코딩 |
| 5 | KSampler | UNet (+ CLIP 참조) | 디퓨전 샘플링 30 steps |
| 6 | VAEDecode | VAE | 잠재 공간 → 이미지 디코딩 |

## 현재 동작: 4개 모델 동시 상주

```
시간 →
CLIP Text   ████████████████████████████████  (로드 후 계속 상주)
CLIP Vision ████████████████████████████████  (로드 후 계속 상주)
UNet        ████████████████████████████████  (로드 후 계속 상주)
VAE         ████████████████████████████████  (로드 후 계속 상주)
            ─────────────────────────────────
피크 VRAM    ~13.7GB (4개 동시)
```

ComfyUI는 노드 실행 완료 후에도 모델을 VRAM에서 내리지 않는다. 다음 생성 시 재로드 없이 바로 사용하기 위한 설계이다.

## 이상적 순차 실행 (목표)

```
시간 →
CLIP Text   ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  인코딩 후 해제
CLIP Vision ░░██░░░░░░░░░░░░░░░░░░░░░░░░░░  인코딩 후 해제
VAE(enc)    ░░░░█░░░░░░░░░░░░░░░░░░░░░░░░░  인코딩 후 해제
UNet        ░░░░░████████████████████████░░  샘플링 (가장 큰 모델)
VAE(dec)    ░░░░░░░░░░░░░░░░░░░░░░░░░░░░██  디코딩 후 해제
            ─────────────────────────────────
피크 VRAM    ~7.7GB (UNet만)
```

VRAM 절감: ~13.7GB → ~7.7GB (**약 44% 감소**)

## 구현 가능성 분석

### 방법 1: ComfyUI 내장 옵션

| 옵션 | 가능 여부 | 설명 |
|------|----------|------|
| `--highvram` | ❌ | 모든 모델 상주 (기본) |
| `--lowvram` | ⚠️ 부분적 | UNet을 레이어별로 GPU↔CPU 스왑. 진정한 순차 해제 아님 |
| `--novram` | ⚠️ 부분적 | 거의 모든 것을 CPU 오프로드. 극도로 느림 |
| 노드별 자동 해제 플래그 | ❌ | 존재하지 않음 |

### 방법 2: 커스텀 노드 개발

ComfyUI 커스텀 노드에서 `comfy.model_management.free_memory(1e30, device)`를 호출하면 강제 해제 가능.

```python
# 예시: UnloadModelsNode (커스텀 노드)
class UnloadModelsNode:
    def execute(self):
        import comfy.model_management
        comfy.model_management.free_memory(1e30, torch.device("cuda"))
        comfy.model_management.soft_empty_cache()
        return ()
```

워크플로우에 CLIP 인코딩 후, UNet 샘플링 전에 이 노드를 삽입하면 CLIP 모델을 해제할 수 있다.

**제약사항**: KSampler가 내부적으로 CLIP 참조를 유지하는 경우 해제가 불완전할 수 있다. 텐서(인코딩 결과)는 유지되지만 모델 자체의 참조가 끊어지는지 검증 필요.

### 방법 3: 워크플로우 분리

1단계와 2단계를 별도 API 호출로 분리:
1. CLIP Text + CLIP Vision + VAE encode → 텐서 저장 → 모델 해제
2. UNet KSampler → VAE decode → 결과 저장

Engine 측에서 ComfyUI API를 2회 호출하는 방식. 가장 확실하지만 워크플로우 2개 관리 필요.

## 기존 lowvram 프로필 (현재 사용 가능)

`animate_comfyui_lowvram` 프로필로 이미 VRAM 절감이 가능하다:

```
CLIP Text    → CPU 오프로드 (VRAM 0GB, RAM ~6.4GB)
CLIP Vision  → GPU (~1.2GB)
UNet         → GPU↔CPU 레이어별 스왑 (~4-5GB VRAM)
VAE          → GPU (~0.3GB)
─────────────
피크 VRAM     ~5-6GB (속도 2~3배 느림)
```

## 비교 요약

| 방식 | 피크 VRAM | 속도 | 구현 난이도 | 상태 |
|------|----------|------|-----------|------|
| 기본 (동시 로드) | ~13.7GB | ~5분 | - | ✅ 구현됨 |
| `--lowvram` 프로필 | ~5-6GB | ~10-15분 | - | ✅ 구현됨 |
| 순차 로드/해제 (커스텀 노드) | ~7.7GB | ~5-6분 | 중간 | ❌ 미구현 |
| 워크플로우 분리 | ~7.7GB | ~5-6분 | 높음 | ❌ 미구현 |

## 결론

- **현재 `--lowvram` 모드가 가장 실용적**인 VRAM 절감 방법 (이미 구현됨)
- 순차 해제는 VRAM을 ~7.7GB로 줄이면서 속도 저하를 최소화할 수 있는 이상적 방법
- 구현 시 **커스텀 노드 방식**이 가장 현실적 (워크플로우 분리보다 간단)
- 추후 VRAM 8~12GB 환경에서 속도 개선이 필요할 때 진행 검토

## 참고 파일

- `ComfyUI/comfy/model_management.py` (481-812줄) — VRAM 관리 핵심
- `ComfyUI/comfy/sd.py` (418-423줄) — CLIP 모델 로딩
- `ComfyUI/comfy/clip_vision.py` (59줄) — CLIP Vision 로딩
- `ComfyUI/comfy/cli_args.py` (137-143줄) — VRAM 플래그 정의
- `conf/workflows/wan21_i2v.json` — WAN 워크플로우 노드 그래프
