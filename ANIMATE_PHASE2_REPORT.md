# Animate Integration — Phase 2 완료 보고서

> Phase 2: 수치 검증 & 순수 로직 이식 (외부 의존성 없음)
> 완료일: 2026-03-18

---

## 1. 작업 범위

ANIMATE_INTEGRATION_PLAN.md 섹션 8 Phase 2에 정의된 4개 항목:

5. `application/use_cases/animate/preprocessing.py` — white_anchor, padding
6. wan_validator.py → `adapters/outbound/animate/numerical_validator.py`
7. wan_keyframe_generator.py → `adapters/outbound/animate/keyframe_generator.py`
8. wan_mask_generator.py → `adapters/outbound/animate/mask_generator.py`

---

## 2. 생성된 파일

| 파일 | 라인 | 원본 | 역할 |
|------|------|------|------|
| `application/use_cases/animate/preprocessing.py` | 114 | wan_backend.py (줄 151-314) | white_anchor 배경 정리 + preprocess_image_simple 캔버스 패딩 |
| `adapters/outbound/animate/mask_generator.py` | 58 | wan_mask_generator.py (104줄) | PilMaskGenerator — MaskGenerationPort 구현 |
| `adapters/outbound/animate/keyframe_generator.py` | 144 | wan_keyframe_generator.py (512줄) | PilKeyframeGenerator — KeyframeGenerationPort 구현 |
| `adapters/outbound/animate/keyframe_travel.py` | 98 | wan_keyframe_generator.py (줄 331-513) | launch/float/parabolic/hop 생성 함수 |
| `adapters/outbound/animate/keyframe_physics.py` | 15 | wan_keyframe_generator.py (줄 110-116) | damped_sin/damped_cos 물리 헬퍼 |
| `adapters/outbound/animate/numerical_validator.py` | 127 | wan_validator.py (708줄) | NumericalAnimationValidator — AnimationValidationPort 구현 |
| `adapters/outbound/animate/validator_metrics.py` | 166 | wan_validator.py (줄 368-709) | 8개 검증 지표 계산 함수 전체 |
| `adapters/outbound/animate/frame_extraction.py` | 58 | wan_validator.py (줄 312-365) | ffmpeg 프레임 추출 + 배경색 감지 + 배경 마스크 |
| `application/use_cases/animate/__init__.py` | 0 | — | 패키지 초기화 |
| `adapters/outbound/animate/__init__.py` | 0 | — | 패키지 초기화 |

### 2.1 preprocessing.py (114L)

**이식 대상**: wan_backend.py의 `_white_anchor()` + `preprocess_image_simple()`

- `white_anchor(image, tolerance)` — 테두리 연결 배경 픽셀을 순백색으로 정리 + UnsharpMask 선명화
- `preprocess_image_simple(image_path, output_path, ...)` — 고정 캔버스(480×480)에 오브젝트 배치 + headroom 패딩

**변경 사항**:
- `Image.LANCZOS` → `Image.Resampling.LANCZOS` (Python 3.11+ Pillow 호환)
- 반환 타입: `str` → `Path` (engine 패턴 준수)
- `preprocess_image()` (프리셋 기반)은 이식하지 않음 — 현재 파이프라인에서 `preprocess_image_simple()`만 사용

### 2.2 mask_generator.py (58L)

**이식 대상**: wan_mask_generator.py 전체 (104줄)

- `PilMaskGenerator.generate(image_path, moving_zone, output_dir)` — MaskGenerationPort 구현
- 파라미터 타입: `str` → `Path` (engine 패턴 준수)
- `os.path` → `pathlib.Path` 전환
- 내부 `from PIL import ImageDraw` → 상단 import로 이동

### 2.3 keyframe_generator.py + keyframe_travel.py + keyframe_physics.py (257L)

**이식 대상**: wan_keyframe_generator.py 전체 (512줄)

원본 512줄을 200L 제약 준수를 위해 3파일로 분할:

| 파일 | 내용 |
|------|------|
| `keyframe_generator.py` (144L) | PilKeyframeGenerator 클래스 — nudge_h/v, wobble, spin, bounce, pop |
| `keyframe_travel.py` (98L) | 모듈 함수 — gen_launch, gen_float, gen_parabolic, gen_hop |
| `keyframe_physics.py` (15L) | damped_sin, damped_cos 물리 헬퍼 |

**변경 사항**:
- 원본 `KFKeyframe`/`KeyframeAnimConfig` dataclass → Phase 1에서 정의한 `KFKeyframe`/`KeyframeAnimation` BaseModel 사용
- 포트 시그니처: `generate(suggested_action, facing_direction, ...)` → `generate(config: KeyframeConfig)` DTO 기반
- dispatch: dict + `.get()` → if-elif 체인 (mypy strict 호환)
- inline if 문 → 표준 if 블록 (ruff E701 준수)

### 2.4 numerical_validator.py + validator_metrics.py + frame_extraction.py (351L)

**이식 대상**: wan_validator.py 전체 (708줄)

원본 708줄을 200L 제약 준수를 위해 3파일로 분할:

| 파일 | 내용 |
|------|------|
| `numerical_validator.py` (127L) | NumericalAnimationValidator 클래스 — 메인 validate() 오케스트레이션 |
| `validator_metrics.py` (166L) | 8개 검증 지표 계산 함수 전체 |
| `frame_extraction.py` (58L) | extract_frames, detect_bg_color, get_bg_mask |

**변경 사항**:
- 원본 `ValidationResult` dataclass → Phase 1의 `AnimationValidation` BaseModel
- 임계값: `__init__` 파라미터 → `AnimationValidationThresholds` DTO (Hydra config 주입)
- 분석 결과: `analysis=None` → `original_analysis: VisionAnalysis` 타입 명시
- numpy 반환 타입: mypy strict에서 `no-any-return` 발생 → `Any` 반환 타입으로 해결

**검증 8개 지표 이식 완료**:
1. `no_motion` — 캐릭터 영역 motion < min_motion × 0.5
2. `too_slow` — char_motion < min_motion
3. `too_fast` — char_motion > max_motion AND raw_motion 교차 검증
4. `repeated_motion` — peaks > max_repeat_peaks
5. `frame_escape` — edge_ratio > max_edge_ratio (bg_drift 억제 포함)
6. `no_return_to_origin` — return_diff > max_return_diff
7. `center_drift` — horizontal_drift > max_center_drift
8. `ghosting` + `background_color_change` — ghost_score + char_brightness_drift

---

## 3. 미이식 항목 및 판단

| 항목 | 판단 |
|------|------|
| `preprocess_image()` (프리셋 기반) | 현재 파이프라인 미사용. `preprocess_image_simple()`만 이식 |
| `WanValidator.__init__` 의 check_* bool 플래그 | 제거 — AnimationValidationThresholds에서 임계값으로 제어. 개별 on/off는 불필요 |
| `_calc_center_drift()` (유클리드 거리) | `_calc_horizontal_drift()`로 대체 — 원본에서도 실제 사용은 horizontal만 |
| `_calc_motion_score()` | `_calc_raw_motion()`으로 이름 변경 (역할 명확화) |

---

## 4. 설계 판단

### 4.1 파일 분할 — 200라인 제약

| 원본 | 원본 라인 | 분할 결과 |
|------|----------|-----------|
| wan_keyframe_generator.py | 512 | keyframe_generator.py(144) + keyframe_travel.py(98) + keyframe_physics.py(15) |
| wan_validator.py | 708 | numerical_validator.py(127) + validator_metrics.py(166) + frame_extraction.py(58) |

### 4.2 numpy 타입 처리

mypy strict 모드에서 numpy의 untyped stub으로 인해 `no-any-return` 에러 발생.
`frame_extraction.py`, `validator_metrics.py`의 numpy 반환 함수 시그니처를 `Any`로 선언하여 해결.
engine 기존 어댑터(`hf_mobilesam.py` 등)도 동일 패턴 사용.

### 4.3 포트 구현 패턴

- `NumericalAnimationValidator` — stateless, `load()/unload()` 없음 (CPU-only, 외부 모델 없음)
- `PilMaskGenerator` — stateless, PIL만 사용
- `PilKeyframeGenerator` — stateless, 순수 연산

이 3개는 AnimationValidationPort, MaskGenerationPort, KeyframeGenerationPort의 stateless 패턴에 부합.

---

## 5. 검증 결과

| 검증 | 결과 |
|------|------|
| `ruff check` | All checks passed |
| `mypy` (10개 파일) | Success: no issues found |
| `pytest` (전체) | **201 passed, 8 skipped, 0 failed** (10.71s) |
| 200라인 제약 | 모든 신규 파일 200L 이하 (최대 166L) |

---

## 6. 커밋 정보

- 커밋: `d73e6d3`
- 브랜치: `wan/test`
- 파일: 10개 생성, 787줄 추가

---

## 7. 다음 단계 — Phase 3

Phase 3: 외부 서비스 어댑터

9. wan_vision_analyzer.py → `adapters/outbound/models/gemini_vision_analyzer.py`
10. wan_mode_classifier.py → `adapters/outbound/models/gemini_mode_classifier.py`
11. wan_ai_validator.py → `adapters/outbound/models/gemini_ai_validator.py`
12. wan_post_motion_classifier.py → `adapters/outbound/models/gemini_post_motion.py`
13. wan_backend.py (ComfyUI 부분) → `adapters/outbound/models/comfyui_animation.py`
14. wan_bg_remover.py → `adapters/outbound/animate/bg_remover.py`
15. wan_lottie_converter.py → `adapters/outbound/animate/lottie_converter.py`
