# Animate Integration — Phase 4 완료 보고서

> Phase 4: Dummy 어댑터 & 테스트
> 완료일: 2026-03-18

---

## 1. 작업 범위

ANIMATE_INTEGRATION_PLAN.md 섹션 8 Phase 4에 정의된 4개 항목:

16. `adapters/outbound/models/dummy_animate.py` — 모든 모델 포트 Dummy
17. `adapters/outbound/animate/dummy_animate.py` — 처리 어댑터 Dummy
18. 단위 테스트: 도메인 엔티티, 전처리, 수치 검증
19. 포트 계약 테스트: 각 Dummy 어댑터

---

## 2. 생성된 파일

| 파일 | 라인 | 역할 |
|------|------|------|
| `adapters/outbound/models/dummy_animate.py` | 133 | 모델 포트 Dummy 5개 |
| `adapters/outbound/animate/dummy_animate.py` | 89 | 처리 어댑터 Dummy 5개 |
| `tests/test_animate_domain.py` | 166 | 도메인 엔티티 단위 테스트 19건 |
| `tests/test_animate_ports_contract.py` | 163 | 포트 계약 테스트 11건 |

### 2.1 models/dummy_animate.py — 모델 포트 Dummy (133L)

모든 모델 포트에 대해 `load(handle) → task() → unload()` 라이프사이클을 구현하는 결정적 Dummy:

| 클래스 | 포트 | 반환값 |
|--------|------|--------|
| `DummyModeClassifier` | ModeClassificationPort | `MOTION_NEEDED`, facing=RIGHT |
| `DummyVisionAnalyzer` | VisionAnalysisPort | bird/wing flap, zone=[0.2,0.1,0.8,0.7], fps=16 |
| `DummyAIValidator` | AIValidationPort | `passed=True` |
| `DummyPostMotionClassifier` | PostMotionClassificationPort | `needs_keyframe=False`, NO_TRAVEL |
| `DummyAnimationGenerator` | AnimationGenerationPort | 더미 MP4 파일 생성 (19바이트), seed/attempt 그대로 반환 |

**DummyVisionAnalyzer 특이사항**:
- `analyze()` — 고정된 VisionAnalysis 반환
- `analyze_with_exclusion()` — `model_copy(update={"action_desc": "alternate action"})` 패턴으로 원본과 다른 action 반환

**DummyAnimationGenerator 특이사항**:
- `generate()`에서 `params.output_dir`에 실제 파일(`{stem}_dummy.mp4`) 생성
- 파일 존재 여부 테스트를 위해 더미 바이트 기록

### 2.2 animate/dummy_animate.py — 처리 어댑터 Dummy (89L)

stateless 포트에 대한 결정적 Dummy:

| 클래스 | 포트 | 반환값 |
|--------|------|--------|
| `DummyAnimationValidator` | AnimationValidationPort | `passed=True`, motion=0.05 |
| `DummyBgRemover` | BackgroundRemovalPort | 4개 더미 PNG 프레임 (tempdir) |
| `DummyKeyframeGenerator` | KeyframeGenerationPort | wobble 3키프레임, 1500ms |
| `DummyFormatConverter` | FormatConversionPort | 빈 ConvertedAsset (경로 없음) |
| `DummyMaskGenerator` | MaskGenerationPort | 더미 mask.png 파일 (tempdir) |

### 2.3 test_animate_domain.py — 도메인 엔티티 단위 테스트 (166L, 19건)

| 테스트 클래스 | 테스트 수 | 검증 내용 |
|-------------|----------|----------|
| `TestEnums` | 4 | ProcessingMode/FacingDirection/MotionTravelType/TravelDirection 값 및 개수 |
| `TestModeClassification` | 2 | 기본값 검증 + JSON roundtrip (model_dump → 복원) |
| `TestVisionAnalysis` | 1 | 생성 + 기본값 (pingpong, bg_type, bg_remove) |
| `TestAnimationGenerationParams` | 1 | 기본값 (pingpong=False, mask_name=None) |
| `TestValidationEntities` | 4 | Thresholds 기본값, Validation 빈 리스트, AIContext 필드, AIFix 기본값 |
| `TestPostMotionResult` | 1 | 기본값 (NO_TRAVEL, NONE, 0.0) |
| `TestKeyframeEntities` | 3 | KeyframeConfig 기본값, KFKeyframe 기본값, KeyframeAnimation 필드 |
| `TestResultEntities` | 3 | AnimationResult 경로, TransparentSequence 빈 리스트, ConvertedAsset None |

### 2.4 test_animate_ports_contract.py — 포트 계약 테스트 (163L, 11건)

모든 10개 포트에 대해 Dummy 어댑터의 계약 준수를 검증:

| 테스트 클래스 | 검증 내용 |
|-------------|----------|
| `TestModeClassifierContract` | load → classify → unload, 반환 타입 ModeClassification |
| `TestVisionAnalyzerContract` | analyze + analyze_with_exclusion, 반환 타입 VisionAnalysis |
| `TestAIValidatorContract` | validate(video, image, context), 반환 타입 AIValidationFix |
| `TestPostMotionClassifierContract` | classify(video, image), 반환 타입 PostMotionResult |
| `TestAnimationGeneratorContract` | generate(handle, image, params), 파일 존재 검증 |
| `TestAnimationValidatorContract` | validate(video, analysis, thresholds), 반환 타입 AnimationValidation |
| `TestBgRemoverContract` | remove(video), 반환 타입 TransparentSequence, 프레임 수 4 |
| `TestKeyframeGeneratorContract` | generate(config), 반환 타입 KeyframeAnimation, 키프레임 수 3 |
| `TestFormatConverterContract` | convert(frames, preset), 반환 타입 ConvertedAsset |
| `TestMaskGeneratorContract` | generate(image, zone), 반환 타입 Path, 파일 존재 |

---

## 3. 설계 판단

### 3.1 Dummy 반환값 선택 기준

- **성공 경로 우선**: 대부분의 Dummy가 `passed=True`, `MOTION_NEEDED` 등 정상 흐름을 반환
- Phase 5 오케스트레이터 통합 테스트에서 전체 파이프라인을 Dummy로 실행할 때 중단 없이 흐르도록 설계
- 실패 경로 테스트는 Phase 5에서 오케스트레이터 테스트 시 Dummy 반환값을 오버라이드하여 검증

### 3.2 파일 생성 Dummy (AnimationGenerator, BgRemover, MaskGenerator)

- 실제 파일을 tempdir에 생성하여 `path.exists()` 검증 가능
- `DummyAnimationGenerator`는 `params.output_dir`에 파일 생성 (orchestrator의 디렉토리 관리와 일관)
- `DummyBgRemover`, `DummyMaskGenerator`는 `tempfile.mkdtemp()`에 자체 디렉토리 생성

### 3.3 TemporaryDirectory 스코프 주의

초기 구현에서 `with tempfile.TemporaryDirectory()` 블록 밖에서 파일 존재를 체크하여 테스트 실패 발생. `assert` 문을 `with` 블록 안으로 이동하여 해결.

### 3.4 단위 테스트 범위

계획서 항목 18에 "전처리, 수치 검증" 단위 테스트도 포함되어 있으나, 이들은 외부 의존성(PIL, numpy, ffmpeg)이 필요하여 Dummy 없이 테스트 불가. Phase 4에서는 **외부 의존성 없는** 도메인 엔티티 테스트에 집중. 전처리/수치 검증의 실제 로직 테스트는 E2E(Phase 6)에서 실제 이미지/비디오로 검증.

---

## 4. 검증 결과

| 검증 | 결과 |
|------|------|
| `ruff check` | All checks passed |
| `mypy` (4개 파일) | Success: no issues found |
| `pytest` (Phase 4 신규) | **30 passed** (0.09s) |
| `pytest` (전체) | **231 passed, 8 skipped, 0 failed** (11.70s) |
| 200라인 제약 | 모든 신규 파일 200L 이하 (최대 166L) |

### 테스트 증가 추이

| Phase | 신규 테스트 | 누적 |
|-------|-----------|------|
| Phase 1 | 0 | 201 |
| Phase 2 | 0 | 201 |
| Phase 3 | 0 | 201 |
| Phase 4 | 30 | 231 |

---

## 5. 커밋 정보

- 커밋: `010e570`
- 브랜치: `wan/test`
- 파일: 4개 생성, +551줄

---

## 6. 다음 단계 — Phase 5

Phase 5: 오케스트레이션 & 부트스트랩

20. `application/use_cases/animate/orchestrator.py` — 메인 파이프라인
21. `application/use_cases/animate/retry_loop.py` — 재시도 전략 (~300L, 헬퍼 5개 포함)
22. `bootstrap/factory.py` — `build_animate_context()` 추가
23. Hydra YAML 설정 파일 작성 (`conf/models/`, `conf/animate_adapters/`)
24. `conf/animate.yaml` 확장
25. `adapters/outbound/models/comfyui_animation.py` — Phase 3에서 이연된 ComfyUI 어댑터
