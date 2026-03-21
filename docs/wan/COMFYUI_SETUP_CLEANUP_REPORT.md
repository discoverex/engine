# COMFYUI_FULL_SETUP.md 정리 보고서

**작성일**: 2026-03-21

## 목적

`COMFYUI_FULL_SETUP.md`에서 ComfyUI 설치에 관한 내용만 남기고, anim_pipeline(sprite_gen) 관련 내용을 분리 정리.

## 삭제한 내용

| 기존 섹션 | 내용 | 삭제 사유 |
|-----------|------|----------|
| 섹션 4 | anim_pipeline 코드 클론 | ComfyUI 설치와 무관 |
| 섹션 5 | anim_pipeline Python 가상환경/의존성 | ComfyUI 설치와 무관 |
| 섹션 9 | 환경변수 설정 (Gemini API, .env, Git, 워크플로우 배치) | engine 측 설정 |
| 섹션 10 | anim_pipeline 실행 확인 (WanBackend 코드) | engine 측 실행 |
| 하단 | 파이프라인 실행 흐름 요약 | engine 파이프라인 설명 |
| 트러블슈팅 | ModuleNotFoundError (anim_pipeline) | ComfyUI와 무관 |

## 추가한 내용

| 항목 | 설명 |
|------|------|
| `.wslconfig` 스왑 설정 (섹션 1-1) | RAM 16GB 환경에서 필수, swap=16GB 권장 |
| VRAM별 실행 옵션 표 | 6GB / 8~12GB / 12GB+ 각각의 ComfyUI 실행 명령어 |
| `--lowvram` + `--reserve-vram` | 6GB VRAM 환경 지원 옵션 설명 |
| WSL OOM 트러블슈팅 | 텍스트 인코더 CPU 오프로드 시 RAM 부족 대응 |
| VRAM별 구성 비교표 | 하드웨어 요구사항에 텍스트 인코더 위치, 생성 속도 비교 추가 |

## 최종 구조

```
1. WSL2 + Ubuntu 설치 (+ .wslconfig 스왑 설정)
2. NVIDIA 드라이버 + CUDA Toolkit
3. 시스템 패키지
4. ComfyUI 설치 (버전 고정 + PyTorch)
5. 커스텀 노드 (GGUF, VHS)
6. WAN 모델 4종 다운로드
7. 실행 확인 (VRAM별 옵션)
+ 트러블슈팅
+ 하드웨어 요구사항
+ 검증 환경
```
