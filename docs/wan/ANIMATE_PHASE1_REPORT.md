# Animate Integration — Phase 1 완료 보고서

> Phase 1: 도메인 & 포트 (의존성 없음)
> 완료일: 2026-03-18

---

## 1. 작업 범위

ANIMATE_INTEGRATION_PLAN.md 섹션 8 Phase 1에 정의된 4개 항목:

1. `domain/animate.py` — Pydantic BaseModel 엔티티 정의
2. `application/ports/animate.py` — 10개 포트 Protocol 정의
3. `config/schema.py` — Animate 설정 스키마 추가
4. `models/types.py` — Request/Response 타입 추가 (필요 시) → 불필요로 판단, 미수행

---

## 2. 생성된 파일

| 파일 | 라인 | 내용 |
|------|------|------|
| `src/discoverex/domain/animate.py` | 146 | Enum 4개 + 분류/분석/검증 BaseModel 10개 |
| `src/discoverex/domain/animate_keyframe.py` | 66 | 키프레임 구조 3개 + 생성 결과 3개 |
| `src/discoverex/application/ports/animate.py` | 152 | Protocol 10개 (포트 인터페이스) |
| `src/discoverex/config/animate_schema.py` | 44 | AnimatePipelineConfig 및 하위 설정 |

### 2.1 domain/animate.py — Enum 및 엔티티 (146L)

**Enum 4개**:
- `ProcessingMode` — KEYFRAME_ONLY / MOTION_NEEDED
- `FacingDirection` — LEFT / RIGHT / UP / DOWN / NONE
- `MotionTravelType` — NO_TRAVEL / TRAVEL_LATERAL / TRAVEL_VERTICAL / TRAVEL_DIAGONAL / AMPLIFY_HOP / AMPLIFY_SWAY / AMPLIFY_FLOAT
- `TravelDirection` — LEFT / RIGHT / UP / DOWN / NONE

**분류/분석 엔티티**:
- `ModeClassification` — Stage 1 분류 결과
- `VisionAnalysis` — Gemini Vision 분석 결과 (모션 파라미터 전체)
- `AnimationGenerationParams` — ComfyUI 워크플로우 실행 파라미터 DTO

**검증 엔티티**:
- `AnimationValidationThresholds` — 수치 검증 임계값 (Hydra config 주입용)
- `AnimationValidation` — 9개 지표 수치 검증 결과
- `AIValidationContext` — AI 검증 요청 시 현재 생성 상태 DTO
- `AIValidationFix` — AI 검증 결과 + 파라미터 보정값

**후처리 분류**:
- `PostMotionResult` — Stage 2 키프레임 트래블 분류 결과

### 2.2 domain/animate_keyframe.py — 키프레임 및 결과 (66L)

**키프레임 구조**:
- `KeyframeConfig` — KeyframeGenerationPort 요청 파라미터
- `KFKeyframe` — 단일 키프레임 (CSS transform 속성 집합)
- `KeyframeAnimation` — 완성된 키프레임 애니메이션 설정

**생성 결과**:
- `AnimationResult` — 비디오 생성 결과 (video_path, seed, attempt)
- `TransparentSequence` — 배경 제거 후 투명 PNG 시퀀스
- `ConvertedAsset` — 포맷 변환 결과 (Lottie/APNG/WebM 경로)

### 2.3 application/ports/animate.py — 포트 인터페이스 (152L)

| 포트 | 라이프사이클 | 역할 |
|------|-------------|------|
| `ModeClassificationPort` | load/classify/unload | KEYFRAME_ONLY vs MOTION_NEEDED 분류 |
| `VisionAnalysisPort` | load/analyze/analyze_with_exclusion/unload | 모션 파라미터 결정 |
| `AIValidationPort` | load/validate/unload | 주관적 품질 평가 + 파라미터 보정 |
| `PostMotionClassificationPort` | load/classify/unload | 키프레임 트래블 분류 |
| `AnimationGenerationPort` | load/generate/unload | ComfyUI WAN I2V 생성 |
| `AnimationValidationPort` | validate (stateless) | 수치 품질 검증 9개 지표 |
| `BackgroundRemovalPort` | remove (stateless) | 배경 제거 → 투명 PNG |
| `KeyframeGenerationPort` | generate (stateless) | CSS 키프레임 생성 |
| `FormatConversionPort` | convert (stateless) | APNG/WebM/Lottie 변환 |
| `MaskGenerationPort` | generate (stateless) | 이동 영역 바이너리 마스크 |

**포트 패턴**:
- Gemini/ComfyUI 포트 → Validator 파이프라인 패턴: `load(handle: ModelHandle) → None` / `task()` / `unload() → None`
- 처리 유틸리티 포트 → stateless: `task()` 단일 메서드

### 2.4 config/animate_schema.py — 설정 스키마 (44L)

- `AnimateModelsConfig` — 5개 모델 포트 Hydra 설정 (mode_classifier, vision_analyzer, animation_generation, ai_validator, post_motion_classifier)
- `AnimateAdaptersConfig` — 5개 처리 어댑터 Hydra 설정 (bg_remover, numerical_validator, mask_generator, keyframe_generator, format_converter)
- `AnimateThresholdsConfig` — 수치 검증 임계값 기본값
- `AnimatePipelineConfig` — 위 3개 조합 + max_retries

---

## 3. 수정된 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/discoverex/domain/__init__.py` | animate, animate_keyframe에서 18개 심볼 re-export 추가 |
| `src/discoverex/application/ports/__init__.py` | animate에서 10개 포트 re-export 추가 |
| `src/discoverex/config/schema.py` | Animate 설정 클래스를 `animate_schema.py`로 분리 (200L 제약 준수) |

---

## 4. 설계 판단

### 4.1 파일 분할 — 200라인 제약

최초 `domain/animate.py`(217L)와 `config/schema.py`(216L)가 아키텍처 테스트(`test_src_python_files_are_200_lines_or_less`)에 위반.

- `domain/animate.py`(217L) → `animate.py`(146L) + `animate_keyframe.py`(66L) 분할
- `config/schema.py`(216L) → Animate 설정을 `animate_schema.py`(44L)로 분리 → `schema.py`(179L)

### 4.2 models/types.py 미수정 판단

계획서 항목 4 "Request/Response 타입 추가 (필요 시)" — animate 전용 타입은 모두 `domain/animate.py`와 `domain/animate_keyframe.py`에 정의됨. 기존 `models/types.py`의 `ModelHandle`만 포트에서 참조하며 추가 타입이 불필요.

### 4.3 Pydantic BaseModel 채택

engine 기존 패턴(Scene, VerificationBundle, ModelHandle 등)과 일관성 유지를 위해 `@dataclass(frozen=True)` 대신 Pydantic `BaseModel` 사용. ANIMATE_INTEGRATION_PLAN.md 코드 레벨 호환성 검증 반영.

---

## 5. 검증 결과

| 검증 | 결과 |
|------|------|
| `ruff check` | All checks passed |
| `mypy` (5개 파일) | Success: no issues found |
| `pytest` (전체) | **201 passed, 8 skipped, 0 failed** (10.70s) |
| 200라인 제약 | 모든 신규/수정 파일 200L 이하 |

---

## 6. 다음 단계 — Phase 2

Phase 2: 수치 검증 & 순수 로직 이식 (외부 의존성 없음)

5. `application/use_cases/animate/preprocessing.py` — white_anchor, padding
6. wan_validator.py → `adapters/outbound/animate/numerical_validator.py`
7. wan_keyframe_generator.py → `adapters/outbound/animate/keyframe_generator.py`
8. wan_mask_generator.py → `adapters/outbound/animate/mask_generator.py`
