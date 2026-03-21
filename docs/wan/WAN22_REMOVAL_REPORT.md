# WAN 2.2 TI2V-5B 프로필 삭제 보고서

**작성일**: 2026-03-21

## 삭제 사유

WAN 2.2 TI2V-5B 프로필은 8GB 이하 VRAM 환경을 위해 도입되었으나, **성능 이슈로 진행 취소**.

### 성능 문제

| 항목 | WAN 2.1 14B | WAN 2.2 5B |
|------|-------------|------------|
| 파라미터 | 14B | 5B (2.8배 적음) |
| 생성 품질 | 높음 | 낮음 |
| CLIPVision | 지원 | 미지원 |
| VAE | 16ch (표준) | 48ch (전용 필요) |

### 기술적 문제 이력

1. **VAE 채널 불일치** — WAN 2.2는 48ch latent 사용, WAN 2.1 VAE(16ch)와 호환 불가
2. **원본 이미지 무시** — `WanImageToVideo` 노드가 WAN 2.2와 비호환
3. **GGUF 텍스트 인코더 VRAM 절감 효과 없음** — GPU 로드 시 FP16 디퀀타이즈

## 대안

6GB VRAM 환경에서는 WAN 2.1 14B + ComfyUI `--lowvram` 플래그로 품질을 유지하면서 동작 가능:

```bash
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 1.0
```

## 삭제된 파일

| 파일 | 설명 |
|------|------|
| `conf/animate_comfyui_wan22.yaml` | WAN 2.2 전용 Hydra 프로필 |
| `conf/workflows/wan22_ti2v_lowvram.json` | WAN 2.2 전용 ComfyUI 워크플로우 |
| `conf/models/animation_generation/comfyui_lowvram.yaml` | WAN 2.2 워크플로우 참조 모델 설정 |

## 코드 정리

| 파일 | 변경 |
|------|------|
| `comfyui_workflow.py` | `Wan22ImageToVideoLatent` 참조 2줄 제거 |
