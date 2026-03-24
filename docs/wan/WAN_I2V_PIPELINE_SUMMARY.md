# WAN I2V Pipeline — 현황 요약

> 작성일: 2026-03-24
> 브랜치: wan/test

---

## 프로젝트 개요

**목표**: 입력 이미지 1장 → 자연스러운 루프 애니메이션 자동 생성 → 웹(Lottie) 배포

**배경**: 비주얼 추론 기반 퍼즐 생성 플랫폼(숨은그림찾기)에서 오브젝트별 자동 애니메이션이 핵심 요구사항

**핵심 원칙**: Gemini Vision이 프리셋 없이 모든 수치(액션·프롬프트·fps·검증 임계값)를 직접 판단하는 자율 루프

---

## 도입 배경

SD 계열(SDXL img2img, FLUX Kontext Pro, FLUX LoRA)로 포즈별 이미지를 생성하는 접근은 캐릭터 정체성 유지에 구조적 한계가 있었음. 원본 1장 → 비디오 생성 → 프레임 추출의 I2V 방식으로 전환하여 해결. WAN 2.2는 VAE latent 채널 불일치(48ch vs 16ch)로 WAN 2.1 I2V-14B GGUF를 채택.

---

## 파이프라인 흐름

```
입력 이미지
  → Stage 1: 모드 분류 (KEYFRAME_ONLY / MOTION_NEEDED)
  → 전처리: Real-ESRGAN 4x 업스케일 + 480×480 캔버스 배치
  → Vision 분석 (Gemini 2.5 Flash) + 마스크 생성
  → WAN I2V 생성 + 이중 검증(수치 8개 + AI) 재시도 루프 (최대 7회)
  → 후처리: rembg U2Net 배경 제거 → APNG/WebM/Lottie 변환
  → Stage 2: 키프레임 이동 판단 + CSS 보강
  → 출력: Lottie JSON (48fps, union bbox, 원본 크기)
```

---

## 핵심 모듈 (11개 포트)

| 모듈 | 구현 클래스 | 역할 |
|------|-----------|------|
| ModeClassificationPort | GeminiModeClassifier | Stage 1: KEYFRAME_ONLY/MOTION_NEEDED 분류 |
| VisionAnalysisPort | GeminiVisionAnalyzer | 액션·프롬프트·fps 등 모든 파라미터 자유 결정 |
| ImageUpscalerPort | SpandrelUpscaler | 소형 이미지(<200px) Real-ESRGAN 4x AI 업스케일 |
| MaskGenerationPort | PilMaskGenerator | moving_zone → 흑백 마스크 PNG (Gaussian blur 경계) |
| AnimationGenerationPort | ComfyUIWanGenerator | ComfyUI API로 WAN 2.1 I2V-14B GGUF 영상 생성 |
| AnimationValidationPort | NumericalAnimationValidator | 수치 검증 9항목 (no_motion~background_color_change) |
| AIValidationPort | GeminiAIValidator | Gemini Vision 5프레임 샘플링 자유 판단 + 수정안 |
| BackgroundRemovalPort | RembgBgRemover | rembg U2Net 시맨틱 세그멘테이션 → 투명 PNG |
| FormatConversionPort | MultiFormatConverter | APNG + WebM + Lottie (48fps, 캔버스 4x, union bbox) |
| PostMotionClassificationPort | GeminiPostMotionClassifier | Stage 2: 7가지 키프레임 이동 분류 |
| KeyframeGenerationPort | PilKeyframeGenerator | 물리 수식 기반 10종 CSS 키프레임 애니메이션 |

---

## WAN 모델

| 모델 | 크기 | VRAM |
|------|------|------|
| wan2.1-i2v-14b-480p-Q3_K_S.gguf | 7.4GB | 6.5GB |
| wan2.1-i2v-14b-480p-Q4_K_S.gguf | 9.8GB | 8.75GB |
| wan2.1-i2v-14b-480p-Q4_K_M.gguf | 11GB | 9.65GB |

---

## 검증 체계

**수치 검증 (9항목)**: no_motion, too_slow, too_fast, repeated_motion, frame_escape, no_return_to_origin, center_drift, ghosting, background_color_change

**AI 검증**: Gemini Vision이 원본+5프레임(0/25/50/75/100%) 비교하여 자유 판단. 실패 시 fps/scale/프롬프트 수정안 직접 결정.

**재시도 전략**: 최대 7회. 연속 품질 실패 3회 → 액션 전환. 연속 no_motion 3회 → 액션 전환. 이력 기반 negative 프롬프트 자동 강화.

---

## Lottie 출력 최적화

| 기능 | 내용 |
|------|------|
| 48fps 업샘플링 | 원본 16fps → 48fps (16×3 정수배), 프리뷰 품질 매칭 |
| 캔버스 4x 확장 | 원본 이미지 대비 4배 투명 캔버스 → 키프레임 이동 시 잘림 방지 |
| 전체 프레임 union bbox | 모든 프레임의 union bbox로 크롭 → 모션 중 날개 등 잘림 방지 |
| 원본 크기 자동 적용 | 480×480 WAN 출력 → 원본 이미지 크기로 자동 리사이즈 |

---

## 대시보드

Flask 기반 REST API(15+ 엔드포인트) + 웹 대시보드(dashboard.html)로 전 과정 GUI 제공. 이미지 업로드 → 분류 → 모션 생성(실시간 프로그레스 바) → 영상 선택 → 배경 제거/Lottie 변환. 설치된 모델만 선택 가능, VRAM 요구량 표시.

---

## 아키텍처

**sprite_gen (원본)**: wan_backend.py가 10개 모듈을 직접 import하는 중심 구조 (6,745줄, 12파일)

**engine (이식)**: 헥사고널 아키텍처(Ports & Adapters). orchestrator가 포트 인터페이스(DI)를 통해 11개 어댑터를 호출. Phase 1~6 완료, 234+ 테스트 통과, mypy strict / ruff 에러 0건.

---

## 미해결 항목 (전부 LOW)

| 항목 | 비고 |
|------|------|
| VRAM 순차 언로드 최적화 | 현재 --lowvram 대응, 44% 절감 가능성 확인 |
| Prefect 워커 배포 검증 | animate job_spec YAML + worker 환경 필요 |
| CLI animate 커맨드 인자 | `--image-path` 인자 추가 필요 |
| 전처리 단위 테스트 추가 | PIL+scipy 합성 이미지 테스트 |

**차단 이슈 0건** — 파이프라인은 실전 동작 상태.
