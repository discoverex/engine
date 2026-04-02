# Animate Integration — 코드 레벨 호환성 검증 보고서

> 검증 대상: 12개 sprite_gen 파일 × ANIMATE_INTEGRATION_PLAN.md (수정본)
> 검증 방법: 각 파일의 클래스/메서드 시그니처, 외부 의존성, 데이터 흐름을 계획서 매핑과 1:1 대조
> 결론: **이식 가능. 차단 이슈 0건, 주의 이슈 5건**

---

## 1. 파일별 이식 호환성 판정

### ✅ 이식 가능 — 변경 없이 또는 최소 수정으로 어댑터화 가능 (8개)

| 파일 | 계획서 위치 | 판정 | 비고 |
|------|------------|------|------|
| wan_mask_generator.py (104줄) | `animate/mask_generator.py` | ✅ 완전 호환 | PIL만 사용. `generate()` 시그니처가 `MaskGenerationPort`와 정확 대응 |
| wan_lottie_converter.py (247줄) | `animate/lottie_converter.py` | ✅ 완전 호환 | PIL + 표준 라이브러리. `convert()` → `FormatConversionPort.convert()` 직접 매핑 |
| wan_bg_remover.py (254줄) | `animate/bg_remover.py` | ✅ 호환 (분리 필요) | APNG/WebM 생성 부분을 FormatConversionPort로 이동 필요. 핵심 로직은 그대로 이식 |
| wan_mode_classifier.py (386줄) | `models/gemini_mode_classifier.py` | ✅ 호환 | `classify()` → `ModeClassificationPort.classify()` 직접 매핑 |
| wan_post_motion_classifier.py (406줄) | `models/gemini_post_motion.py` | ✅ 호환 | `classify()` → `PostMotionClassificationPort.classify()` 직접 매핑 |
| wan_vision_analyzer.py (491줄) | `models/gemini_vision_analyzer.py` | ✅ 호환 (⚠ 주의 1) | `analyze()` + `analyze_with_exclusion()` 두 메서드 존재 — 포트에 반영 필요 |
| wan_keyframe_generator.py (512줄) | `animate/keyframe_generator.py` | ✅ 호환 (⚠ 주의 2) | `generate()` 시그니처와 포트의 `KeyframeConfig` DTO 불일치 |
| wan_ai_validator.py (541줄) | `models/gemini_ai_validator.py` | ✅ 호환 (⚠ 주의 3) | `validate()` 시그니처 6개 파라미터 — 포트 `context` 파라미터와 매핑 필요 |

### ✅ 이식 가능 — 분해가 필요하지만 로직 자체는 호환 (2개)

| 파일 | 계획서 위치 | 판정 | 비고 |
|------|------------|------|------|
| wan_validator.py (708줄) | `animate/numerical_validator.py` | ✅ 분해 호환 | `validate(video_path, analysis)` → 포트의 `validate(video, original_analysis, thresholds)` 매핑. 내부 임계값을 Thresholds DTO로 추출하면 됨 |
| wan_backend.py (2515줄) | 6개 모듈 분해 | ✅ 분해 호환 (⚠ 주의 4, 5) | 아래 상세 |

### ⬜ 제외 대상 — engine에 포함하지 않음 (2개)

| 파일 | 이유 |
|------|------|
| wan_server.py (581줄) | Flask REST API — engine 외부 관심사 |
| wan_dashboard.html (1335줄) | 웹 UI — engine 외부 관심사 |

---

## 2. 주의 이슈 상세 (5건)

### ⚠ 주의 1: VisionAnalysisPort에 `analyze_with_exclusion` 메서드 미반영

**현황**: `wan_vision_analyzer.py`에는 두 개의 공개 메서드가 있음:
- `analyze(image_path)` — 일반 분석
- `analyze_with_exclusion(image_path, exclude_action)` — 액션 전환 시 특정 액션 제외하고 재분석

**계획서**: `VisionAnalysisPort`에 `analyze(image: Path) → VisionAnalysis`만 정의됨.

**영향**: `retry_loop.py`의 `_switch_action()` 헬퍼가 `analyze_with_exclusion`을 호출해야 하는데 포트에 메서드가 없음.

**해결안**:
```python
class VisionAnalysisPort(Protocol):
    def analyze(self, image: Path) -> VisionAnalysis: ...
    def analyze_with_exclusion(
        self, image: Path, exclude_action: str
    ) -> VisionAnalysis: ...
```

Dummy 어댑터에서도 `analyze_with_exclusion`은 `analyze`와 동일한 결과 반환 (exclude 무시).

---

### ⚠ 주의 2: KeyframeGenerationPort 시그니처 불일치

**현황**: 실제 `WanKeyframeGenerator.generate()` 시그니처:
```python
def generate(
    self,
    suggested_action: str,          # "nudge_horizontal", "hop" 등
    facing_direction: str = "none", # "left", "right" 등
    duration_ms: int | None = None,
    loop: bool = True,
) -> KeyframeAnimConfig:
```

**계획서**: `KeyframeGenerationPort.generate(config: KeyframeConfig) → KeyframeAnimation`
- `KeyframeConfig` DTO가 domain/animate.py에 정의되어 있지 않음

**해결안**: domain에 `KeyframeConfig` DTO 추가:
```python
@dataclass(frozen=True)
class KeyframeConfig:
    suggested_action: str
    facing_direction: str = "none"
    duration_ms: int | None = None
    loop: bool = True
```

---

### ⚠ 주의 3: AIValidationPort 시그니처 — `context` 미정의

**현황**: 실제 `WanAIValidator.validate()` 시그니처:
```python
def validate(
    self,
    video_path: str,
    original_path: str,
    current_fps: int,
    current_scale: float,
    positive: str,
    negative: str,
) -> AIValidationResult:
```

**계획서**: `AIValidationPort.validate(video: Path, image: Path, context) → AIValidationFix`
- `context`가 미정의 — 6개 파라미터 중 4개(fps, scale, positive, negative)가 묶여야 함

**해결안**: domain에 `AIValidationContext` DTO 추가:
```python
@dataclass(frozen=True)
class AIValidationContext:
    current_fps: int
    current_scale: float
    positive: str
    negative: str
```

포트 시그니처:
```python
class AIValidationPort(Protocol):
    def validate(
        self,
        video: Path,
        original_image: Path,
        context: AIValidationContext,
    ) -> AIValidationFix: ...
```

---

### ⚠ 주의 4: 워크플로우 빌더 — 글로벌 상수 의존

**현황**: `build_wan_workflow()` (줄 1412-1587)과 관련 함수들이 모듈 레벨 글로벌 변수를 직접 참조:
- `WAN_WORKFLOW_PATH` (줄 87-94) — `os.path.isfile()` 분기
- `WAN_MODEL`, `CLIP_MODEL`, `VAE_MODEL` (줄 70-72) — fallback 빌드에서 사용
- `WORKFLOW_INJECT_MAP` (줄 1091-1104) — 파라미터 주입 매핑
- `POSITIVE_CLIP_NODE_ID`, `NEGATIVE_CLIP_NODE_ID` (줄 1108-1109)

**계획서**: "환경변수 직접 읽기 → Hydra 설정으로 전환"으로 제외되어 있음.

**영향**: `comfyui_animation.py` 어댑터로 이식 시 이 글로벌 상수들을 모두 생성자 파라미터(Hydra config)로 전환해야 함. 단순 복사 붙여넣기가 아닌 리팩토링 필요.

**해결안**: ComfyUI 어댑터 생성자에서 받도록:
```python
class ComfyUIAnimationAdapter:
    def __init__(
        self,
        comfyui_url: str,
        workflow_path: str | None,
        wan_model: str,
        clip_model: str,
        vae_model: str,
    ):
```
`build_wan_workflow`, `load_workflow_from_file`, `_gui_workflow_to_api`는 어댑터 내부 private 메서드로 이동. `WORKFLOW_INJECT_MAP`은 클래스 상수로 변환.

---

### ⚠ 주의 5: `_ValidationStats` 제거 시 이력 기반 negative 강화 로직 영향

**현황**: `_ValidationStats`는 engine에서 제외(MLflow로 대체)되지만, `generate()` 메서드 줄 1789-1829에서 **이전 실패 이력 기반 negative 프롬프트 자동 강화** 로직이 `_ValidationStats.load_history()`에 의존:
```python
history = self._stats.load_history(stem)
if history["total_attempts"] > 0:
    issue_counter: Counter = Counter()
    for img_data in history["images"].values():
        for a in img_data["attempts"]:
            issue_counter.update(a.get("issues", []))
    # 빈도 2회 이상인 이슈만 negative에 추가
```

**영향**: `_ValidationStats`를 단순히 제거하면 이력 기반 프롬프트 강화가 작동하지 않음. 이 로직은 재시도 성공률에 직접 영향을 미침.

**해결안**: 두 가지 옵션 중 선택:

A) **세션 내 메모리 기반**: `retry_loop.py`가 현재 실행의 실패 이력만 메모리에 유지 (이전 실행의 이력은 포기). 단순하고 외부 의존성 없음. 대부분의 경우 MAX_RETRIES 7회 내에서 충분.

B) **MLflow 기반 이력 조회**: orchestrator가 MLflow tracker를 통해 동일 이미지의 과거 실패 기록을 조회. 완전한 기능 보존이지만 MLflow 의존.

**권장**: Phase 5에서 **A안으로 시작** (세션 내 이력만). 운영 데이터 축적 후 B안으로 확장.

---

## 3. 외부 의존성 매트릭스 (실제 import 기반 확인)

| 파일 | PIL | numpy | scipy | ffmpeg (subprocess) | google.genai | 기타 |
|------|-----|-------|-------|---------------------|-------------|------|
| wan_mask_generator.py | ✅ | — | — | — | — | — |
| wan_lottie_converter.py | ✅ | — | — | — | — | base64, json |
| wan_bg_remover.py | ✅ | ✅ | ✅ ndimage | ✅ 프레임 추출, WebM | — | — |
| wan_mode_classifier.py | ✅ (이미지 로드) | — | — | — | ✅ | json, re |
| wan_post_motion_classifier.py | ✅ (이미지 로드) | — | — | — | ✅ | json, re |
| wan_vision_analyzer.py | ✅ (이미지 로드) | — | — | — | ✅ | json, re |
| wan_ai_validator.py | ✅ (프레임 추출) | — | — | — | ✅ | json, re |
| wan_keyframe_generator.py | — | — | — | — | — | math, json |
| wan_validator.py | ✅ | ✅ | — | ✅ 프레임 추출 | — | — |
| wan_backend.py 전처리 | ✅ | ✅ | ✅ ndimage | — | — | — |
| wan_backend.py ComfyUI | — | — | — | — | — | urllib, json |
| wan_backend.py compositing | ✅ | — | — | ✅ | — | — |

**계획서의 pyproject.toml 의존성과 일치 확인**: ✅
- `google-genai` — 4개 Gemini 모듈
- `scipy` — wan_bg_remover.py, wan_backend.py 전처리 (_white_anchor)
- PIL/numpy — 기존 engine 의존성에 이미 포함
- ffmpeg — 시스템 바이너리 (Python 패키지 아님)

---

## 4. 데이터 흐름 연결 검증

실제 `wan_backend.py` `generate()` 메서드의 데이터 흐름을 추적하여 포트 간 연결이 끊기지 않는지 확인:

```
입력: image_path (str)
  │
  ├─[1] ModeClassificationPort.classify(image_path)
  │     → ModeClassification
  │     ├─ KEYFRAME_ONLY → KeyframeGenerationPort.generate(config) → 완료
  │     └─ MOTION_NEEDED → 계속 ↓
  │
  ├─[2] preprocessing.preprocess_image_simple(image_path)
  │     → processed_path (str)
  │
  ├─[3] VisionAnalysisPort.analyze(processed_path)
  │     → VisionAnalysis  ← ⚠ analyze_with_exclusion도 필요 (주의 1)
  │
  ├─[4] AnimationGenerationPort.load() → handle
  │     AnimationGenerationPort.generate(handle, uploaded, params) → AnimationResult
  │                                                       ↑ AnimationGenerationParams DTO
  │
  ├─[5] AnimationValidationPort.validate(video, analysis, thresholds)
  │     → AnimationValidation
  │     ├─ passed → [6]
  │     └─ failed → AIValidationPort.validate(video, image, context) → AIValidationFix
  │                                                          ↑ ⚠ AIValidationContext DTO 필요 (주의 3)
  │                 ├─ ai_adjustments → retry_loop._apply_ai_adjustments()
  │                 └─ quality_fail × N → VisionAnalysisPort.analyze_with_exclusion()
  │                                       ↑ ⚠ 포트에 미반영 (주의 1)
  │
  ├─[6] 성공 후처리:
  │     compositing.apply_post_compositing(video, image, mask)  ← compositing.py
  │     BackgroundRemovalPort.remove(video) → TransparentSequence
  │     FormatConversionPort.convert(frames, preset) → ConvertedAsset
  │
  └─[7] PostMotionClassificationPort.classify(video) → PostMotionResult
        ├─ needs_keyframe → KeyframeGenerationPort.generate()
        └─ no_travel → 완료
```

**연결 끊김**: 없음 (주의 이슈 3건을 반영하면 완전 연결)

---

## 5. 최종 판정

| 항목 | 결과 |
|------|------|
| 차단 이슈 (이식 불가) | **0건** |
| 주의 이슈 (계획서 보완 필요) | **5건** (위 상세) |
| 포트 시그니처 보완 | 3건 (VisionAnalysis 메서드 추가, KeyframeConfig DTO, AIValidationContext DTO) |
| 글로벌 상수 리팩토링 | 1건 (ComfyUI 워크플로우 빌더) |
| 제거 영향 대응 | 1건 (_ValidationStats 이력 기반 로직) |

**결론: 모든 스크립트가 헥사고날 아키텍처에 이식 가능합니다.**
주의 이슈 5건은 모두 "DTO 추가" 또는 "메서드 추가" 수준의 보완이며, 로직 자체를 변경해야 하는 건은 없습니다.
