# ANIMATE_INTEGRATION_PLAN 검토 결과 및 수정 지시

> 원본: `ANIMATE_INTEGRATION_PLAN.md`
> 검토 기준: wan_backend.py(2515줄) + 11개 모듈 실제 코드 교차 검증
> 용도: Claude Code에 전달하여 계획서 수정 반영

---

## 수정 1. `VisionAnalysis` 엔티티 필드 누락 보정

**위치**: 섹션 2.2 `domain/animate.py` — `VisionAnalysis` dataclass

**문제**: 실제 `VisionAnalysisResult`(wan_vision_analyzer.py 33-51줄)에 존재하는 `reason: str`과 `from_llm: bool` 필드가 계획서에서 누락됨. `reason`은 wan_backend.py 줄 1726에서 로깅에 사용됨.

**수정**:

```python
@dataclass(frozen=True)
class VisionAnalysis:
    object_desc: str
    action_desc: str
    moving_parts: str             # ← 수정 2 참조 (list[str] → str)
    fixed_parts: str              # ← 수정 2 참조 (list[str] → str)
    moving_zone: tuple[float, float, float, float]
    frame_rate: int
    frame_count: int
    min_motion: float
    max_motion: float
    max_diff: float
    positive: str
    negative: str
    pingpong: bool
    bg_type: str
    bg_remove: bool
    reason: str                   # ← 추가: 판단 근거 (로깅용)
```

`from_llm: bool`은 디버깅 전용이므로 도메인 엔티티에서 제외. 어댑터 내부에서만 사용.

---

## 수정 2. `VisionAnalysis.moving_parts` / `fixed_parts` 타입 수정

**위치**: 섹션 2.2 `domain/animate.py` — `VisionAnalysis` dataclass

**문제**: 계획서에 `moving_parts: list[str]`, `fixed_parts: list[str]`로 기재되어 있으나, 실제 `VisionAnalysisResult`(wan_vision_analyzer.py 37-38줄)에서는 둘 다 `str` 타입. Gemini가 반환하는 값이 "left wing, right wing" 같은 단일 설명 문자열이지 분리된 목록이 아님.

**수정**: `moving_parts: str`, `fixed_parts: str`로 변경.

향후 `list[str]`로 정규화하고 싶다면 어댑터 레이어에서 파싱 후 변환하는 것은 가능하나, Phase 1에서는 원본 동작 동등성을 우선하여 `str` 유지.

---

## 수정 3. `PostMotionResult` 엔티티 — Enum 타입 명시 + 필드 보정

**위치**: 섹션 2.2 `domain/animate.py` — `PostMotionResult` dataclass

**문제**:
- 계획서의 `travel_type: str`, `travel_direction: str`이 실제로는 `MotionTravelType`, `TravelDirection` Enum (wan_post_motion_classifier.py 48-65줄)
- `reason: str` 필드 누락 (실제 코드에 존재, wan_backend.py 줄 2339에서 로깅 사용)

**수정**:

```python
# domain/animate.py에 Enum도 함께 정의

class MotionTravelType(str, Enum):
    NO_TRAVEL       = "no_travel"
    TRAVEL_LATERAL  = "travel_lateral"
    TRAVEL_VERTICAL = "travel_vertical"
    TRAVEL_DIAGONAL = "travel_diagonal"
    AMPLIFY_HOP     = "amplify_hop"
    AMPLIFY_SWAY    = "amplify_sway"
    AMPLIFY_FLOAT   = "amplify_float"

class TravelDirection(str, Enum):
    LEFT  = "left"
    RIGHT = "right"
    UP    = "up"
    DOWN  = "down"
    NONE  = "none"

@dataclass(frozen=True)
class PostMotionResult:
    needs_keyframe: bool
    travel_type: MotionTravelType       # ← str → Enum
    travel_direction: TravelDirection    # ← str → Enum
    confidence: float
    suggested_keyframe: str | None
    reason: str                          # ← 추가
```

`ModeClassification`도 동일 패턴 적용 — `ProcessingMode`, `FacingDirection` Enum을 `domain/animate.py`에 포함:

```python
class ProcessingMode(str, Enum):
    KEYFRAME_ONLY = "keyframe_only"
    MOTION_NEEDED = "motion_needed"

class FacingDirection(str, Enum):
    LEFT  = "left"
    RIGHT = "right"
    UP    = "up"
    DOWN  = "down"
    NONE  = "none"

@dataclass(frozen=True)
class ModeClassification:
    processing_mode: ProcessingMode
    has_deformable: bool
    is_scene: bool
    subject_desc: str
    facing_direction: FacingDirection
    suggested_action: str
    reason: str                          # ← 추가 (wan_backend.py 줄 1696)
```

---

## 수정 4. `AnimationGenerationPort.generate()` — 파라미터 DTO 추가

**위치**: 섹션 2.1 포트 인터페이스 테이블 + 섹션 2.2 도메인 엔티티

**문제**: 계획서의 `generate(handle, image, params) → AnimationResult`에서 `params`가 미정의. 실제 `_generate_one`(wan_backend.py 2473-2516줄)은 11개 파라미터를 받음. 타입 안전성과 IDE 자동완성을 위해 전용 DTO 필요.

**수정**: `domain/animate.py`에 DTO 추가, 포트 시그니처 갱신:

```python
@dataclass(frozen=True)
class AnimationGenerationParams:
    """ComfyUI 워크플로우 실행에 필요한 파라미터 묶음."""
    positive: str
    negative: str
    frame_rate: int
    frame_count: int
    seed: int
    output_dir: str            # 결과 MP4 저장 디렉토리
    stem: str                  # 파일명 기본 stem
    attempt: int               # 시도 번호
    pingpong: bool = False
    mask_name: str | None = None
```

포트 시그니처:

```python
class AnimationGenerationPort(Protocol):
    def load(self) -> Any: ...
    def generate(
        self,
        handle: Any,
        uploaded_image: str,
        params: AnimationGenerationParams,
    ) -> AnimationResult: ...
    def unload(self) -> None: ...
```

---

## 수정 5. 재시도 루프 복잡도 재추정 + 중복 코드 정리 지시

**위치**: 섹션 2.5 `animate/retry_loop.py` + 섹션 3 분해 계획

**문제**: 계획서 `~150L` 추정은 과소. 실제 `generate()` 메서드(줄 1648-2224, 576줄)에 다음 복잡도가 있음:

| 로직 | 줄 범위 | 줄 수 |
|------|---------|-------|
| 프롬프트 구성 (base + adj + history negative) | 1757-1840 | ~83 |
| AI 검증 통과 후 처리 (soft_pass, compositing, bg_remove) | 1888-1972 | ~84 |
| AI 검증 실패 → 연속 품질 실패 → 액션 전환 | 1973-2055 | ~82 |
| 수치 검증 실패 → no_motion 분기 → 액션 전환 | 2056-2197 | ~141 |
| 루프 종료 처리 | 2199-2223 | ~24 |

중복 코드 2건:
1. **액션 전환 로직** — AI 실패 경로(줄 1991-2033)와 수치 실패 경로(줄 2080-2108, 2134-2173)에 동일한 `analyze_with_exclusion` + 프롬프트 재구성 + 마스크 재생성 코드가 3회 반복
2. **AI 조정 적용** — AI 검증 실패 후(줄 2036-2055)와 수치 실패 후(줄 2177-2197)에 동일한 fps/scale/positive/negative 적용 코드가 2회 반복

**수정**:

1. `retry_loop.py` 추정치를 `~150L` → `~300L`로 변경
2. 섹션 3 분해 계획에 다음 내부 헬퍼 메서드 추출 지시 추가:

```
animate/retry_loop.py (~300L)
  ├── RetryLoop.__init__()           — 카운터, 임계값 초기화
  ├── RetryLoop.run()                — 메인 루프
  ├── RetryLoop._build_prompts()     — base + adj + history → 최종 prompt
  ├── RetryLoop._switch_action()     — analyze_with_exclusion + 프롬프트/마스크 재구성 (중복 제거)
  ├── RetryLoop._apply_ai_adjustments() — fps/scale/positive/negative 적용 (중복 제거)
  └── RetryLoop._handle_success()    — soft_pass, compositing, bg_remove
```

---

## 수정 6. `_apply_post_compositing` 위치 지정

**위치**: 섹션 3 분해 계획 — "post_compositing (orchestrator 내부 private 메서드)"

**문제**: 실제로 `_apply_post_compositing()`은 wan_backend.py 줄 1252-1328의 **모듈 레벨 독립 함수**이며, WanBackend 클래스 메서드가 아님. PIL + numpy + ffmpeg를 사용하는 영상 처리 로직으로, orchestrator 내부에 두기에는 외부 의존성이 많음.

**수정**: 별도 모듈로 분리:

```
adapters/outbound/animate/
  ├── bg_remover.py
  ├── mask_generator.py
  ├── keyframe_generator.py
  ├── lottie_converter.py
  ├── compositing.py              ← 신규: _apply_post_compositing 이동
  └── dummy_animate.py
```

섹션 3 다이어그램도 갱신:

```
wan_backend.py (2515L)
  ├─→ [Use Case] animate/orchestrator.py (~300L)
  ├─→ [Use Case] animate/retry_loop.py (~300L)
  ├─→ [Use Case] animate/preprocessing.py (~100L)
  ├─→ [Adapter] models/comfyui_animation.py (~250L)
  ├─→ [Adapter] animate/bg_remover.py (~200L)
  └─→ [Adapter] animate/compositing.py (~80L)    ← 추가
```

포트 인터페이스 추가 필요 여부: 현재는 ComfyUI 전용 후처리이므로 포트 없이 직접 호출로 시작. 향후 다른 비디오 생성기에서도 합성이 필요하면 포트로 승격.

---

## 수정 7. `wan_validator.py` — "도메인 서비스" → 어댑터로 재배치

**위치**: 섹션 8 실행 순서 Phase 2 항목 6

**문제**: 계획서에서 wan_validator.py를 "수치 검증 로직을 도메인 서비스로 이식 (numpy만 사용)"으로 기재했으나, 실제 `WanValidator`(wan_validator.py)는:
- PIL로 프레임 추출
- numpy로 옵티컬 플로우 + 배경 마스크 계산
- ffmpeg로 영상 디코딩
- scipy.ndimage로 flood fill

순수 도메인 로직이 아니라 외부 라이브러리 의존 영상 분석 코드.

**수정**:

도메인에는 **임계값 + 판정 규칙**만 배치:

```python
# domain/animate.py에 추가

@dataclass(frozen=True)
class AnimationValidationThresholds:
    """수치 검증 임계값 — Hydra config에서 주입."""
    min_motion: float = 0.003
    max_motion: float = 0.15
    max_repeat_peaks: int = 12
    max_return_diff: float = 0.40
    max_center_drift: float = 0.12
```

실제 검증 로직은 `AnimationValidationPort` 어댑터로 배치:

```
adapters/outbound/animate/
  └── numerical_validator.py      ← wan_validator.py 이식 (PIL+numpy+ffmpeg)
```

섹션 2.1 포트 테이블 수정:

| 포트 | 수정 전 | 수정 후 |
|------|---------|---------|
| AnimationValidationPort | `validate(video, thresholds) → AnimationValidation` | `validate(video, original_analysis, thresholds) → AnimationValidation` |

`original_analysis` 추가 이유: 실제 `WanValidator.validate()`가 `analysis: VisionAnalysisResult`를 받아 동작별 임계값을 조회함 (wan_validator.py 참조).

섹션 8 Phase 2 항목 6 수정:

```
수정 전: wan_validator.py → 수치 검증 로직을 도메인 서비스로 이식 (numpy만 사용)
수정 후: wan_validator.py → adapters/outbound/animate/numerical_validator.py (AnimationValidationPort 구현)
         임계값만 domain/animate.py의 AnimationValidationThresholds로 분리
```

---

## 추가 제안. 배경 제거 / 포맷 변환 책임 경계 명확화

**위치**: 섹션 2.1 + 2.3

**현황**: `wan_bg_remover.py`가 현재 3가지를 동시에 수행:
1. 배경 제거 → 투명 PNG 시퀀스
2. APNG 생성 (`_save_apng`)
3. WebM 생성 (`_save_webm`)

한편 `wan_lottie_converter.py`는 Lottie JSON 변환만 담당.

**제안**: 포트 책임을 다음과 같이 정리하면 깔끔함:

```
BackgroundRemovalPort.remove(video) → TransparentSequence(frames: list[Path])
  ← 투명 PNG 시퀀스 생성까지만 담당

FormatConversionPort.convert(frames, preset) → ConvertedAsset
  ← APNG, WebM, Lottie 변환 모두 담당
```

이 경우 `TransparentSequence`에서 `apng_path`, `webm_path` 필드를 제거하고 `ConvertedAsset`으로 통합:

```python
@dataclass(frozen=True)
class TransparentSequence:
    frames: list[Path]
    # apng_path, webm_path 제거 — FormatConversionPort 책임

@dataclass(frozen=True)
class ConvertedAsset:
    lottie_path: Path | None
    apng_path: Path | None
    webm_path: Path | None
```

이 제안은 선택사항. 현재 구조대로 진행해도 동작에는 문제 없음.

---

## 수정 반영 후 최종 디렉토리 구조 (섹션 9 갱신분)

변경된 부분만 표시:

```
src/discoverex/
├── domain/
│   └── animate.py                    # Enum 6개 + 엔티티 10개 + Thresholds 1개
├── application/
│   └── use_cases/
│       └── animate/
│           ├── orchestrator.py       # ~300L (수정 5 반영)
│           ├── retry_loop.py         # ~300L (수정 5 반영, 150→300)
│           └── preprocessing.py      # ~100L
├── adapters/outbound/
│   ├── models/
│   │   └── comfyui_animation.py      # AnimationGenerationParams DTO 사용 (수정 4)
│   └── animate/
│       ├── bg_remover.py
│       ├── mask_generator.py
│       ├── keyframe_generator.py
│       ├── lottie_converter.py
│       ├── compositing.py            # ← 신규 (수정 6)
│       ├── numerical_validator.py    # ← 신규 (수정 7, 도메인→어댑터 이동)
│       └── dummy_animate.py
```

---

## 체크리스트 (Claude Code 작업 시 참조)

- [ ] 수정 1: VisionAnalysis에 `reason: str` 필드 추가
- [ ] 수정 2: VisionAnalysis `moving_parts`, `fixed_parts` → `str` 타입으로 수정
- [ ] 수정 3: PostMotionResult, ModeClassification에 Enum 타입 적용 + `reason` 필드 추가
- [ ] 수정 4: `AnimationGenerationParams` DTO 추가, 포트 시그니처 갱신
- [ ] 수정 5: retry_loop.py 추정치 300L로 갱신, 내부 헬퍼 5개 명시, 중복 2건 정리 지시 추가
- [ ] 수정 6: compositing.py 별도 모듈 추가, 섹션 3/9 디렉토리 구조 갱신
- [ ] 수정 7: wan_validator.py를 도메인 서비스 → 어댑터(`numerical_validator.py`)로 재배치, Thresholds만 도메인에 유지
- [ ] 추가 제안: 배경 제거/포맷 변환 책임 분리 (선택)
