# Animate Pipeline Integration Plan

> sprite_gen (anim_pipeline) → engine 헥사고널 아키텍처 적용 계획

## 1. 현재 상태

### 1.1 sprite_gen (소스)

`/home/snake2/anim_pipeline/image_pipeline/sprite_gen/` — 6,745라인, 12개 파일.

정적 이미지에서 게임용 스프라이트 애니메이션을 자동 생성하는 파이프라인:

```
입력 이미지
  → [Mode 분류] KEYFRAME_ONLY / MOTION_NEEDED
  → [Vision 분석] Gemini로 모션 파라미터 결정
  → [WAN I2V 생성] ComfyUI 워크플로우 실행 (최대 7회 재시도)
  → [수치 검증] 9개 품질 지표
  → [AI 검증] Gemini Vision 주관 평가 + 파라미터 보정
  → [후처리 분류] 키프레임 트래블 필요 여부
  → [배경 제거] 투명 PNG 시퀀스
  → [포맷 변환] APNG / WebM / Lottie JSON
```

| 파일 | 라인 | 역할 |
|------|------|------|
| wan_backend.py | 2515 | 전체 오케스트레이션 + ComfyUI 통신 + 전처리 + 후합성 |
| wan_validator.py | 708 | 수치 기반 품질 검증 (9개 지표) |
| wan_server.py | 581 | Flask REST API + 대시보드 |
| wan_vision_analyzer.py | 491 | Gemini Vision → 모션 파라미터 |
| wan_keyframe_generator.py | 512 | CSS 키프레임 애니메이션 생성 |
| wan_ai_validator.py | 541 | Gemini Vision 주관 품질 평가 |
| wan_post_motion_classifier.py | 406 | 후처리 키프레임 트래블 분류 |
| wan_mode_classifier.py | 386 | KEYFRAME_ONLY vs MOTION_NEEDED 분류 |
| wan_bg_remover.py | 254 | 배경 제거 → 투명 PNG/APNG/WebM |
| wan_lottie_converter.py | 247 | Lottie JSON 변환 |
| wan_mask_generator.py | 104 | 이동 영역 바이너리 마스크 |

### 1.2 engine (타겟) — animate 스캐폴딩 현황

animate 인프라가 **이미 완전히 와이어링**되어 있음:

- CLI: `discoverex animate --scene-jsons ...` 커맨드 존재
- Prefect: `run_animate_job_flow()` 등록/배포 가능
- Config: `conf/animate.yaml` → `conf/flows/animate/stub.yaml`
- Schema: `FlowsConfig.animate: HydraComponentConfig` 필드 존재
- Bootstrap: `engine_entry.py`에서 animate 커맨드 라우팅 완비
- 테스트: `test_engine_job_v2_accepts_animate_without_required_args()` 존재

**현재 stub 상태**: `animate_stub()` → `"animate flow is not implemented yet"` 반환

---

## 2. 아키텍처 매핑

### 2.1 신규 포트 인터페이스

`src/discoverex/application/ports/`에 추가할 포트:

```
ports/
├── models.py              (기존 — 아래 포트 추가)
└── animate.py             (신규)
```

| 포트 | 메서드 시그니처 | sprite_gen 원본 |
|------|----------------|-----------------|
| **ModeClassificationPort** | `load(handle: ModelHandle) → None` / `classify(image: Path) → ModeClassification` / `unload() → None` | wan_mode_classifier.py |
| **VisionAnalysisPort** | `load(handle: ModelHandle) → None` / `analyze(image: Path) → VisionAnalysis` / `analyze_with_exclusion(image: Path, exclude_action: str) → VisionAnalysis` / `unload() → None` | wan_vision_analyzer.py |
| **AnimationGenerationPort** | `load(handle: ModelHandle) → None` / `generate(handle: ModelHandle, uploaded_image: str, params: AnimationGenerationParams) → AnimationResult` / `unload() → None` | wan_backend.py (ComfyUI 부분) |
| **AnimationValidationPort** | `validate(video: Path, original_analysis: VisionAnalysis, thresholds: AnimationValidationThresholds) → AnimationValidation` | wan_validator.py |
| **AIValidationPort** | `load(handle: ModelHandle) → None` / `validate(video: Path, original_image: Path, context: AIValidationContext) → AIValidationFix` / `unload() → None` | wan_ai_validator.py |
| **PostMotionClassificationPort** | `load(handle: ModelHandle) → None` / `classify(video: Path, original_image: Path) → PostMotionResult` / `unload() → None` | wan_post_motion_classifier.py |
| **BackgroundRemovalPort** | `remove(video: Path, config) → TransparentSequence` | wan_bg_remover.py |
| **KeyframeGenerationPort** | `generate(config: KeyframeConfig) → KeyframeAnimation` | wan_keyframe_generator.py |
| **FormatConversionPort** | `convert(frames: list[Path], preset) → ConvertedAsset` | wan_lottie_converter.py |
| **MaskGenerationPort** | `generate(zone, image_size) → Path` | wan_mask_generator.py |

**설계 판단 — Gemini/ComfyUI 포트의 `load()/unload()` 패턴**:

Gemini 기반 4개 포트 + ComfyUI 포트는 engine의 기존 ML 모델과 달리 PyTorch 모델 로딩이 아닌 API 클라이언트 초기화를 수행한다. engine Validator 파이프라인의 `load(handle: ModelHandle) → None` / `unload() → None` 패턴을 따르되, `load()`에서는 API 키 검증 및 클라이언트 초기화를, `unload()`에서는 리소스 정리를 수행한다. `ModelHandle`은 API 키, 모델명, 엔드포인트 등 런타임 메타데이터를 전달하는 용도로 활용.

**설계 판단 — Gemini 포트 분리 여부**:

ModeClassification, VisionAnalysis, AIValidation, PostMotionClassification 4개 포트 모두 Gemini Vision API를 사용한다. 두 가지 접근이 가능:

- **A) 개별 포트 유지 (권장)**: 각 포트가 독립적인 도메인 책임을 가짐. Gemini 어댑터 4개가 동일 SDK를 공유하되, 프롬프트/파싱이 완전히 다르므로 별도 어댑터가 자연스러움. 향후 특정 단계만 다른 LLM으로 교체 가능.
- **B) VisionLLMPort 통합**: 범용 `query(image, prompt) → JSON` 포트 하나로 묶음. 프롬프트 로직이 어댑터 밖으로 유출되어 헥사고널 원칙 위반.

### 2.2 도메인 엔티티 확장

`src/discoverex/domain/`에 추가:

**타입 컨벤션**: engine 기존 패턴에 맞춰 도메인 엔티티는 **Pydantic `BaseModel`** 사용 (engine의 `Scene`, `VerificationBundle`, `ModelHandle` 등과 일관성 유지). 검증 결과처럼 단순 반환값은 **`TypedDict(total=False)`** 패턴도 가능.

```python
# domain/animate.py (신규)
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field

# --- Enum 정의 ---

class ProcessingMode(str, Enum):
    KEYFRAME_ONLY = "keyframe_only"
    MOTION_NEEDED = "motion_needed"

class FacingDirection(str, Enum):
    LEFT  = "left"
    RIGHT = "right"
    UP    = "up"
    DOWN  = "down"
    NONE  = "none"

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

# --- 분류/분석 엔티티 ---

class ModeClassification(BaseModel):
    processing_mode: ProcessingMode
    has_deformable: bool
    is_scene: bool = False
    subject_desc: str = ""
    facing_direction: FacingDirection = FacingDirection.NONE
    suggested_action: str = ""
    reason: str = ""                     # 판단 근거 (로깅용)

class VisionAnalysis(BaseModel):
    object_desc: str
    action_desc: str
    moving_parts: str                    # Gemini 반환값 그대로 ("left wing, right wing")
    fixed_parts: str                     # 동일 — 단일 설명 문자열
    moving_zone: list[float]             # [x1, y1, x2, y2] relative coords (Gemini JSON 반환값)
    frame_rate: int
    frame_count: int
    min_motion: float
    max_motion: float
    max_diff: float
    positive: str                        # WAN 중국어 프롬프트
    negative: str
    pingpong: bool = True
    bg_type: str = "solid"
    bg_remove: bool = True
    reason: str = ""                     # 판단 근거 (로깅용)

# --- 생성 파라미터 DTO ---

class AnimationGenerationParams(BaseModel):
    """ComfyUI 워크플로우 실행에 필요한 파라미터 묶음."""
    positive: str
    negative: str
    frame_rate: int
    frame_count: int
    seed: int
    output_dir: str
    stem: str
    attempt: int
    pingpong: bool = False
    mask_name: str | None = None

# --- 검증 엔티티 ---

class AnimationValidationThresholds(BaseModel):
    """수치 검증 임계값 — Hydra config에서 주입."""
    min_motion: float = 0.003
    max_motion: float = 0.15
    max_repeat_peaks: int = 12
    max_edge_ratio: float = 0.08
    max_return_diff: float = 0.40
    max_center_drift: float = 0.12

class AnimationValidation(BaseModel):
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)  # no_motion, too_slow, ...
    scores: dict[str, float] = Field(default_factory=dict)

class AIValidationContext(BaseModel):
    """AIValidationPort.validate()에 전달하는 현재 생성 상태."""
    current_fps: int
    current_scale: float
    positive: str
    negative: str

class AIValidationFix(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    reason: str = ""
    frame_rate: int | None = None
    scale: float | None = None
    positive: str | None = None
    negative: str | None = None

# --- 후처리 분류 ---

class PostMotionResult(BaseModel):
    needs_keyframe: bool
    travel_type: MotionTravelType = MotionTravelType.NO_TRAVEL
    travel_direction: TravelDirection = TravelDirection.NONE
    confidence: float = 0.0
    suggested_keyframe: str = ""
    reason: str = ""                     # 판단 근거 (로깅용)

# --- 키프레임 ---

class KeyframeConfig(BaseModel):
    """KeyframeGenerationPort.generate()에 전달하는 요청 파라미터."""
    suggested_action: str              # "nudge_horizontal", "hop", "wobble" 등
    facing_direction: str = "none"     # "left", "right", "up", "down", "none"
    duration_ms: int | None = None
    loop: bool = True

class KFKeyframe(BaseModel):
    """단일 키프레임 — CSS transform 속성 집합."""
    t: float                             # 시간 (0.0~1.0)
    translateX: float = 0.0
    translateY: float = 0.0
    rotate: float = 0.0
    scaleX: float = 1.0
    scaleY: float = 1.0
    opacity: float = 1.0
    glow_color: str | None = None
    glow_radius: float | None = None

class KeyframeAnimation(BaseModel):
    animation_type: str
    keyframes: list[KFKeyframe]
    duration_ms: int
    easing: str
    transform_origin: str = "center center"
    loop: bool = True
    suggested_action: str = ""
    facing_direction: str = ""

# --- 생성 결과 ---

class AnimationResult(BaseModel):
    video_path: Path
    seed: int
    attempt: int

class TransparentSequence(BaseModel):
    frames: list[Path] = Field(default_factory=list)
    # APNG/WebM 생성은 FormatConversionPort 책임

class ConvertedAsset(BaseModel):
    lottie_path: Path | None = None
    apng_path: Path | None = None
    webm_path: Path | None = None
```

### 2.3 어댑터 구현 배치

```
src/discoverex/adapters/outbound/
├── models/                        (기존)
│   ├── ...                        (기존 어댑터들)
│   ├── comfyui_animation.py       (신규 — AnimationGenerationPort 구현)
│   ├── gemini_mode_classifier.py  (신규 — ModeClassificationPort)
│   ├── gemini_vision_analyzer.py  (신규 — VisionAnalysisPort)
│   ├── gemini_ai_validator.py     (신규 — AIValidationPort)
│   ├── gemini_post_motion.py      (신규 — PostMotionClassificationPort)
│   └── dummy_animate.py           (신규 — 전체 Dummy 어댑터)
├── animate/                       (신규)
│   ├── bg_remover.py              (BackgroundRemovalPort — PIL/ffmpeg/scipy)
│   ├── numerical_validator.py     (AnimationValidationPort — PIL/numpy/ffmpeg/scipy)
│   ├── compositing.py             (후합성 — PIL/numpy/ffmpeg, 포트 없이 직접 호출)
│   ├── mask_generator.py          (MaskGenerationPort — PIL)
│   ├── keyframe_generator.py      (KeyframeGenerationPort — 순수 연산)
│   ├── lottie_converter.py        (FormatConversionPort — PIL/base64)
│   └── dummy_animate.py           (Dummy 어댑터)
└── ...
```

**배치 근거**:
- ComfyUI, Gemini 어댑터 → `models/`: ML 모델/AI 서비스 호출이므로 기존 모델 어댑터 패턴과 동일한 위치
- 배경 제거, 수치 검증, 합성, 마스크, 키프레임, Lottie → `animate/`: AI 모델이 아닌 영상/이미지 처리 유틸리티이므로 별도 카테고리

**책임 경계 — 배경 제거 vs 포맷 변환**:
- `BackgroundRemovalPort.remove()` → 투명 PNG 시퀀스 생성까지만 담당 (`TransparentSequence.frames`)
- `FormatConversionPort.convert()` → APNG, WebM, Lottie 변환 모두 담당 (`ConvertedAsset`)
- 원본 `wan_bg_remover.py`에서 APNG/WebM 생성을 함께 수행하던 것을 분리하여 단일 책임 원칙 준수

### 2.4 Hydra 설정

```
conf/
├── models/
│   ├── animation_generation/
│   │   ├── comfyui.yaml           # ComfyUI WAN I2V
│   │   └── dummy.yaml
│   ├── mode_classifier/
│   │   ├── gemini.yaml            # Gemini Vision
│   │   └── dummy.yaml
│   ├── vision_analyzer/
│   │   ├── gemini.yaml
│   │   └── dummy.yaml
│   ├── ai_validator/
│   │   ├── gemini.yaml
│   │   └── dummy.yaml
│   └── post_motion_classifier/
│       ├── gemini.yaml
│       └── dummy.yaml
├── animate_adapters/
│   ├── bg_remover/
│   │   ├── ffmpeg.yaml
│   │   └── dummy.yaml
│   ├── numerical_validator/
│   │   ├── default.yaml           # PIL/numpy/ffmpeg 기반 수치 검증
│   │   └── dummy.yaml
│   ├── mask_generator/
│   │   ├── pil.yaml
│   │   └── dummy.yaml
│   ├── keyframe_generator/
│   │   ├── default.yaml
│   │   └── dummy.yaml
│   └── format_converter/
│       ├── lottie.yaml
│       └── dummy.yaml
└── animate.yaml                   # 기존 파일 확장 — 위 설정 조합
```

### 2.5 Use Case — Animate 오케스트레이션

```
src/discoverex/application/use_cases/
├── gen_verify/          (기존)
├── validator/           (기존)
└── animate/             (신규)
    ├── __init__.py
    ├── orchestrator.py  # AnimateOrchestrator — 메인 파이프라인 조율
    ├── retry_loop.py    # 재시도 + AI 피드백 반영 로직
    └── preprocessing.py # 이미지 전처리 (white_anchor, padding 등)
```

### 2.6 Bootstrap 확장

`src/discoverex/bootstrap/factory.py`에 추가:

```python
def build_animate_context(config: AnimatePipelineConfig) -> AnimateOrchestrator:
    # 1. 모델 포트 인스턴스화
    mode_classifier = instantiate(cfg.models.mode_classifier.as_kwargs())
    vision_analyzer = instantiate(cfg.models.vision_analyzer.as_kwargs())
    animation_generator = instantiate(cfg.models.animation_generation.as_kwargs())
    animation_validator = instantiate(cfg.models.ai_validator.as_kwargs())
    post_motion = instantiate(cfg.models.post_motion_classifier.as_kwargs())

    # 2. 처리 어댑터 인스턴스화
    bg_remover = instantiate(cfg.animate_adapters.bg_remover.as_kwargs())
    mask_generator = instantiate(cfg.animate_adapters.mask_generator.as_kwargs())
    keyframe_generator = instantiate(cfg.animate_adapters.keyframe_generator.as_kwargs())
    format_converter = instantiate(cfg.animate_adapters.format_converter.as_kwargs())

    # 3. 수치 검증 어댑터 인스턴스화 (PIL/numpy/ffmpeg 의존)
    numerical_validator = instantiate(cfg.animate_adapters.numerical_validator.as_kwargs())

    return AnimateOrchestrator(...)
```

### 2.7 Config Schema 확장

`src/discoverex/config/schema.py`에 추가:

```python
class AnimateModelsConfig(BaseModel):
    mode_classifier: HydraComponentConfig
    vision_analyzer: HydraComponentConfig
    animation_generation: HydraComponentConfig
    ai_validator: HydraComponentConfig
    post_motion_classifier: HydraComponentConfig

class AnimateAdaptersConfig(BaseModel):
    bg_remover: HydraComponentConfig
    numerical_validator: HydraComponentConfig
    mask_generator: HydraComponentConfig
    keyframe_generator: HydraComponentConfig
    format_converter: HydraComponentConfig

class AnimatePipelineConfig(BaseModel):
    models: AnimateModelsConfig
    animate_adapters: AnimateAdaptersConfig
    thresholds: AnimationValidationThresholds
    max_retries: int = 7
```

---

## 3. wan_backend.py 분해 계획

현재 2,515라인 God Object를 6개 모듈로 분해:

```
wan_backend.py (2515L)
  ├─→ [Use Case] animate/orchestrator.py (~300L)
  │     전체 파이프라인 흐름 제어
  │     포트 인터페이스만 참조
  │
  ├─→ [Use Case] animate/retry_loop.py (~300L)
  │     재시도 전략 (최대 7회, seed 변경, 파라미터 보정)
  │     내부 헬퍼 메서드로 중복 코드 정리:
  │       RetryLoop._build_prompts()          — base + adj + history → 최종 prompt
  │       RetryLoop._switch_action()          — analyze_with_exclusion + 프롬프트/마스크 재구성
  │       RetryLoop._apply_ai_adjustments()   — fps/scale/positive/negative 적용
  │       RetryLoop._handle_success()         — soft_pass, compositing, bg_remove
  │     ※ 원본에서 액션 전환 로직 3회 중복, AI 조정 적용 2회 중복 → 헬퍼로 통합
  │     ※ _ValidationStats 제거 대응:
  │       원본은 파일 기반 이력(_ValidationStats.load_history)으로 이전 실패의
  │       빈도 2회 이상 이슈를 negative 프롬프트에 자동 추가하는 로직이 있음.
  │       → 세션 내 메모리 기반으로 대체: RetryLoop이 현재 실행의 실패 이력을
  │         dict[str, Counter]로 유지하며 _build_prompts()에서 참조.
  │       → 이전 실행 이력은 포기 (MAX_RETRIES 7회 내에서 충분).
  │       → 운영 데이터 축적 후 MLflow tracker 기반 이력 조회로 확장 가능.
  │
  ├─→ [Use Case] animate/preprocessing.py (~100L)
  │     white_anchor, padding, 리사이즈
  │     도메인 로직 (외부 의존성 없음)
  │
  ├─→ [Adapter] models/comfyui_animation.py (~250L)
  │     ComfyUIClient (HTTP 통신)
  │     워크플로우 로딩/주입/큐잉/폴링
  │     load(handle) → generate(handle, image, params) → unload() 라이프사이클
  │     ※ 글로벌 상수 리팩토링: 원본의 모듈 레벨 환경변수 참조를
  │       생성자 파라미터(Hydra config)로 전환:
  │       __init__(comfyui_url, workflow_path, wan_model, clip_model, vae_model,
  │                positive_clip_node_id, negative_clip_node_id)
  │     ※ WORKFLOW_INJECT_MAP → 클래스 상수로 이동
  │     ※ build_wan_workflow, load_workflow_from_file,
  │       _gui_workflow_to_api → 어댑터 내부 private 메서드
  │
  ├─→ [Adapter] animate/bg_remover.py (~200L)
  │     ffmpeg 프레임 추출
  │     PIL 배경 제거
  │     투명 PNG 시퀀스 생성 (APNG/WebM은 FormatConversionPort 위임)
  │
  └─→ [Adapter] animate/compositing.py (~80L)
        _apply_post_compositing — 마스크 기반 픽셀 합성
        ※ 원본은 모듈 레벨 독립 함수 (줄 1252-1328)
        ※ PIL + numpy + ffmpeg 사용으로 orchestrator 외부에 배치
        ※ 현재는 ComfyUI 전용 후처리이므로 포트 없이 직접 호출.
           향후 다른 비디오 생성기에서도 필요하면 포트로 승격
```

---

## 4. 제외 항목

다음은 engine에 **포함하지 않음**:

| 항목 | 이유 |
|------|------|
| `wan_server.py` (Flask REST API) | engine은 CLI/Prefect 진입점만 소유. REST API는 별도 서빙 레이어 |
| `wan_dashboard.html` (웹 UI) | 동일 — engine 외부 관심사 |
| `_ValidationStats` 파일 기반 통계 | engine은 MLflow tracker로 메트릭 기록. 파일 기반 통계 불필요 |
| 환경변수 직접 읽기 패턴 | Hydra 설정으로 전환 |
| 글로벌 상수 (`MAX_RETRIES=7`) | config에서 주입 |

---

## 5. 외부 의존성 추가

`pyproject.toml`에 새로운 optional extra 그룹 추가:

```toml
[project.optional-dependencies]
animate = [
    "google-genai>=1.0.0",     # Gemini Vision API
    "scipy>=1.11.0",           # flood fill (배경 제거)
]
animate-gpu = [
    "google-genai>=1.0.0",
    "scipy>=1.11.0",
]
```

**외부 런타임 요구사항** (Python 패키지 외):
- ComfyUI 서버 (별도 프로세스, HTTP API로 통신)
- ffmpeg (시스템 바이너리, 프레임 추출/WebM 인코딩)
- Gemini API 키 (`GEMINI_API_KEY` 환경변수 또는 Hydra 설정)

---

## 6. Dummy 어댑터 — 테스트 전략

모든 포트에 대해 결정적 Dummy 어댑터를 만들어 GPU/API 없이 테스트 가능하게 함:

```python
# adapters/outbound/models/dummy_animate.py

class DummyModeClassifier:
    """ModeClassificationPort Dummy 구현."""
    def load(self, handle: ModelHandle) -> None: pass
    def classify(self, image: Path) -> ModeClassification:
        return ModeClassification(
            processing_mode=ProcessingMode.MOTION_NEEDED,
            has_deformable=True, is_scene=False,
            subject_desc="test_sprite",
            facing_direction=FacingDirection.RIGHT,
            suggested_action="walk",
            reason="dummy classification",
        )
    def unload(self) -> None: pass

class DummyVisionAnalyzer:
    """VisionAnalysisPort Dummy 구현."""
    def load(self, handle: ModelHandle) -> None: pass
    def analyze(self, image: Path) -> VisionAnalysis:
        return VisionAnalysis(
            object_desc="test bird", action_desc="wing flap",
            moving_parts="left wing, right wing", fixed_parts="body, legs",
            moving_zone=[0.2, 0.1, 0.8, 0.7],
            frame_rate=16, frame_count=32,
            min_motion=0.03, max_motion=0.15, max_diff=0.20,
            positive="鸟扇动翅膀", negative="静止",
            reason="dummy analysis",
        )
    def analyze_with_exclusion(self, image: Path, exclude_action: str) -> VisionAnalysis:
        result = self.analyze(image)
        return result.model_copy(update={"action_desc": "alternate action"})
    def unload(self) -> None: pass

class DummyAnimationGenerator:
    """AnimationGenerationPort Dummy 구현."""
    def load(self, handle: ModelHandle) -> None: pass
    def generate(self, handle: ModelHandle, uploaded_image: str, params: AnimationGenerationParams) -> AnimationResult:
        # 더미 MP4 파일 생성 (단색 프레임)
        return AnimationResult(video_path=Path("/tmp/dummy.mp4"), seed=42, attempt=1)
    def unload(self) -> None: pass

# ... 나머지 포트별 Dummy (AIValidation, PostMotion 등 동일 패턴)
```

**테스트 계층**:

| 테스트 유형 | 대상 | 어댑터 |
|------------|------|--------|
| 단위 테스트 | 도메인 엔티티, 전처리, 수치 검증 로직 | 없음 (순수 함수) |
| 포트 계약 테스트 | 각 포트 인터페이스 준수 여부 | Dummy |
| 통합 테스트 | 오케스트레이터 전체 흐름 | Dummy 전체 |
| E2E 스모크 | ComfyUI + Gemini 실제 호출 | 실제 어댑터 |

---

## 7. 기존 코드 수정 범위

engine 기존 파일 중 수정이 필요한 항목:

| 파일 | 변경 내용 |
|------|-----------|
| `src/discoverex/config/schema.py` | `AnimateModelsConfig`, `AnimateAdaptersConfig`, `AnimatePipelineConfig` 추가 |
| `src/discoverex/bootstrap/factory.py` | `build_animate_context()` 팩토리 함수 추가 |
| `src/discoverex/flows/subflows.py` | `animate_stub()` → 실제 구현으로 교체 |
| `conf/animate.yaml` | stub 대신 실제 모델/어댑터 설정 조합 참조 |
| `conf/flows/animate/` | 실제 animate flow 설정 추가 |
| `src/discoverex/application/ports/` | animate 포트 인터페이스 파일 추가 |
| `src/discoverex/domain/` | animate 도메인 엔티티 파일 추가 |
| `pyproject.toml` | `animate` optional extra 추가 |

---

## 8. 실행 순서

### Phase 1: 도메인 & 포트 (의존성 없음)

1. `domain/animate.py` — Pydantic BaseModel 엔티티 정의 (Enum 4개 + 모델 14개)
2. `application/ports/animate.py` — 10개 포트 Protocol 정의
3. `config/schema.py` — Animate 설정 스키마 추가
4. `models/types.py` — Request/Response 타입 추가 (필요 시)

### Phase 2: 수치 검증 & 순수 로직 이식 (외부 의존성 없음)

5. `application/use_cases/animate/preprocessing.py` — white_anchor, padding
6. wan_validator.py → `adapters/outbound/animate/numerical_validator.py` (AnimationValidationPort 구현, PIL/numpy/ffmpeg/scipy). 임계값만 `domain/animate.py`의 `AnimationValidationThresholds`로 분리
7. wan_keyframe_generator.py → `adapters/outbound/animate/keyframe_generator.py` (순수 연산)
8. wan_mask_generator.py → `adapters/outbound/animate/mask_generator.py` (PIL)

### Phase 3: 외부 서비스 어댑터

9. wan_vision_analyzer.py → `adapters/outbound/models/gemini_vision_analyzer.py`
10. wan_mode_classifier.py → `adapters/outbound/models/gemini_mode_classifier.py`
11. wan_ai_validator.py → `adapters/outbound/models/gemini_ai_validator.py`
12. wan_post_motion_classifier.py → `adapters/outbound/models/gemini_post_motion.py`
13. wan_backend.py (ComfyUI 부분) → `adapters/outbound/models/comfyui_animation.py`
14. wan_bg_remover.py → `adapters/outbound/animate/bg_remover.py`
15. wan_lottie_converter.py → `adapters/outbound/animate/lottie_converter.py`

### Phase 4: Dummy 어댑터 & 테스트

16. `adapters/outbound/models/dummy_animate.py` — 모든 모델 포트 Dummy
17. `adapters/outbound/animate/dummy_animate.py` — 처리 어댑터 Dummy
18. 단위 테스트: 도메인 엔티티, 전처리, 수치 검증
19. 포트 계약 테스트: 각 Dummy 어댑터

### Phase 5: 오케스트레이션 & 부트스트랩

20. `application/use_cases/animate/orchestrator.py` — 메인 파이프라인
21. `application/use_cases/animate/retry_loop.py` — 재시도 전략 (~300L, 헬퍼 5개 포함)
22. `bootstrap/factory.py` — `build_animate_context()` 추가
23. Hydra YAML 설정 파일 작성 (`conf/models/`, `conf/animate_adapters/`)
24. `conf/animate.yaml` 확장

### Phase 6: Flow 연결 & E2E

25. `flows/subflows.py` — animate_stub → 실제 구현 교체
26. 통합 테스트: Dummy 어댑터로 전체 흐름
27. E2E 스모크: 실제 ComfyUI + Gemini 연동
28. Prefect 배포 검증: `bin/cli prefect deploy-flow animate --branch <branch>`

---

## 9. 최종 디렉토리 구조 (신규 파일만)

```
src/discoverex/
├── domain/
│   └── animate.py                              # Enum 4개 + BaseModel 엔티티 14개 (KFKeyframe, AIValidationContext 포함)
├── application/
│   ├── ports/
│   │   └── animate.py                          # 10개 Protocol
│   └── use_cases/
│       └── animate/
│           ├── __init__.py
│           ├── orchestrator.py                  # 파이프라인 조율 (~300L)
│           ├── retry_loop.py                    # 재시도 전략 (~300L, 헬퍼 5개)
│           └── preprocessing.py                 # 이미지 전처리 (~100L)
├── adapters/outbound/
│   ├── models/
│   │   ├── comfyui_animation.py                # ComfyUI HTTP 어댑터 (~250L)
│   │   ├── gemini_mode_classifier.py           # Gemini 모드 분류
│   │   ├── gemini_vision_analyzer.py           # Gemini 비전 분석
│   │   ├── gemini_ai_validator.py              # Gemini AI 검증
│   │   ├── gemini_post_motion.py               # Gemini 후처리 분류
│   │   └── dummy_animate.py                    # 모델 Dummy 전체
│   └── animate/
│       ├── __init__.py
│       ├── bg_remover.py                       # 배경 제거 (~200L)
│       ├── numerical_validator.py              # 수치 품질 검증 (PIL/numpy/ffmpeg/scipy)
│       ├── compositing.py                      # 마스크 기반 후합성 (~80L)
│       ├── mask_generator.py                   # 마스크 생성
│       ├── keyframe_generator.py               # CSS 키프레임
│       ├── lottie_converter.py                 # Lottie 변환
│       └── dummy_animate.py                    # 처리 Dummy 전체
├── config/
│   └── schema.py                               # (수정) Animate 스키마 추가
└── bootstrap/
    └── factory.py                              # (수정) build_animate_context 추가

conf/
├── models/
│   ├── animation_generation/
│   │   ├── comfyui.yaml
│   │   └── dummy.yaml
│   ├── mode_classifier/
│   │   ├── gemini.yaml
│   │   └── dummy.yaml
│   ├── vision_analyzer/
│   │   ├── gemini.yaml
│   │   └── dummy.yaml
│   ├── ai_validator/
│   │   ├── gemini.yaml
│   │   └── dummy.yaml
│   └── post_motion_classifier/
│       ├── gemini.yaml
│       └── dummy.yaml
├── animate_adapters/
│   ├── bg_remover/
│   │   ├── ffmpeg.yaml
│   │   └── dummy.yaml
│   ├── numerical_validator/
│   │   ├── default.yaml
│   │   └── dummy.yaml
│   ├── mask_generator/
│   │   ├── pil.yaml
│   │   └── dummy.yaml
│   ├── keyframe_generator/
│   │   ├── default.yaml
│   │   └── dummy.yaml
│   └── format_converter/
│       ├── lottie.yaml
│       └── dummy.yaml
└── animate.yaml                                # (수정) 실제 설정 조합

tests/
├── test_animate_domain.py                      # 도메인 엔티티 테스트
├── test_animate_preprocessing.py               # 전처리 순수 함수
├── test_animate_numerical_validator.py         # 수치 검증 로직
├── test_animate_ports_contract.py              # 포트 계약 준수
├── test_animate_orchestrator.py                # Dummy 통합 테스트
└── test_animate_e2e.py                         # 실제 서비스 E2E
```

---

## 10. 리스크 & 완화 전략

| 리스크 | 영향 | 완화 |
|--------|------|------|
| ComfyUI 서버 가용성 | animate 전체 불가 | Dummy 어댑터로 CI 보호. E2E는 별도 GPU 환경에서만 실행 |
| Gemini API 비용/레이트 | 4개 모듈이 호출 | API 키 풀링, 캐시 레이어 고려. Dummy로 개발/테스트 커버 |
| wan_backend.py 분해 시 로직 유실 | 재시도 루프 미묘한 분기 누락 | 원본 대비 동작 동등성 테스트 작성. 원본 테스트 시나리오 이식 |
| ffmpeg 시스템 의존성 | CI 환경에 ffmpeg 없을 수 있음 | bg_remover Dummy 어댑터로 CI 우회. ffmpeg 필요 테스트는 마커로 분리 |
| VRAM 피크 (ComfyUI + engine 동시) | OOM | engine의 기존 순차 로딩 패턴 적용. animate flow는 generate/verify와 별도 프로세스 |
