# Animate Integration — Phase 1-2 확인 사항 정리

> Phase 1 (도메인 & 포트) + Phase 2 (수치 검증 & 순수 로직 이식) 완료 후
> Phase 3 착수 전 확인이 필요한 항목 종합

---

## 1. 이전 리뷰 지적 정정

### 1.1 ghosting / background_color_change는 수치 검증기에 존재함 (정정)

이전 Phase 2 리뷰에서 "ghosting과 background_color_change는 wan_ai_validator.py(AI 검증)의 이슈 키워드이지 수치 검증기의 항목이 아니다"라고 지적했으나, 이는 **오류**.

원본 wan_validator.py 확인 결과:
- 줄 261-274: `_calc_ghost_score()` → `failed_checks.append("ghosting")` — 수치 검증 항목
- 줄 276-299: `_calc_bg_drift()` + `_calc_char_brightness_drift()` → `failed_checks.append("background_color_change")` — 수치 검증 항목

따라서 원본 수치 검증기의 `failed_checks` 문자열은 **9개**:
`no_motion`, `too_slow`, `too_fast`, `repeated_motion`, `frame_escape`, `no_return_to_origin`, `center_drift`, `ghosting`, `background_color_change`

Phase 2 보고서의 "8개 지표 + ghosting/background_color_change" 기술은 정확함. 확인 완료, 추가 조치 불필요.

---

## 2. Phase 1 확인 사항

### 2.1 `domain/__init__.py` re-export 완전성 [LOW]

**상태**: 보고서에 "18개 심볼 re-export 추가" 언급, 구체적 목록 미기재.

**필요 심볼 (18개)**:

`animate.py`에서 12개:
- `ProcessingMode`, `FacingDirection`, `MotionTravelType`, `TravelDirection`
- `ModeClassification`, `VisionAnalysis`, `AnimationGenerationParams`
- `AnimationValidationThresholds`, `AnimationValidation`
- `AIValidationContext`, `AIValidationFix`, `PostMotionResult`

`animate_keyframe.py`에서 6개:
- `KeyframeConfig`, `KFKeyframe`, `KeyframeAnimation`
- `AnimationResult`, `TransparentSequence`, `ConvertedAsset`

**확인 방법**: Phase 3에서 어댑터가 `from discoverex.domain import VisionAnalysis` 패턴으로 import할 때 자동 확인됨.

**리스크**: LOW — 누락 시 ImportError로 즉시 발견.

### 2.2 `ports/__init__.py` re-export 완전성 [LOW]

**상태**: 보고서에 "10개 포트 re-export 추가" 언급.

**필요 심볼 (10개)**:
- `ModeClassificationPort`, `VisionAnalysisPort`, `AIValidationPort`
- `PostMotionClassificationPort`, `AnimationGenerationPort`
- `AnimationValidationPort`, `BackgroundRemovalPort`
- `KeyframeGenerationPort`, `FormatConversionPort`, `MaskGenerationPort`

**리스크**: LOW — 동일.

---

## 3. Phase 2 확인 사항

### 3.1 검증 지표 수 불일치 표기 [RESOLVED]

Phase 2 보고서 제목에 "8개 지표"로 표기, 실제 이식은 9개.
보고서 섹션 2.4 마지막에 "8. ghosting + background_color_change"로 묶어서 기술.

**결론**: 이식 자체는 정확. 보고서 표기만 "8개 → 9개"로 정정하면 됨. 코드 영향 없음.

### 3.2 check_* bool 플래그 제거 영향 [LOW]

**원본**: `WanValidator.__init__`에 `check_motion=True`, `check_too_slow=True` 등 8개 bool 플래그.
**이식 후**: 제거 — `AnimationValidationThresholds`의 임계값으로 제어.

**검증 필요**: 원본에서 외부 코드가 `WanValidator(check_frame_escape=False)` 등으로 특정 검증을 끄는 패턴이 있는지.

**결과**: wan_backend.py에서 `self.validator = WanValidator()` (줄 1616) — 기본값만 사용, 플래그 변경 없음. wan_server.py에서도 동일. **영향 없음 확인**.

### 3.3 `_calc_center_drift` → `_calc_horizontal_drift` 대체 [LOW]

**원본**: `_calc_center_drift()`(유클리드 거리)와 `_calc_horizontal_drift()` 둘 다 존재.
실제 `validate()` 메서드(줄 253)에서 `_calc_horizontal_drift()`만 호출.
`_calc_center_drift()`는 메서드로 정의되어 있지만 validate()에서 미사용.

**결론**: Phase 2에서 `_calc_horizontal_drift()`만 이식한 것은 정확. 데드 코드 제거.

### 3.4 preprocessing — `preprocess_image()` (프리셋 기반) 미이식 [LOW]

**원본**: wan_backend.py에 `preprocess_image()`(줄 214-260)과 `preprocess_image_simple()`(줄 263-314) 두 함수 존재.

**확인**: `generate()` 메서드(줄 1715)에서 `preprocess_image_simple()`만 호출. `preprocess_image()`는 `WanPreset` 클래스를 인자로 받지만, `WanPreset` import 자체가 주석처리(줄 49 `# wan_presets 불필요`).

**결론**: 데드 코드 미이식 — 정확.

### 3.5 numpy Any 반환 타입 — mypy 호환성 [LOW]

**상태**: `frame_extraction.py`, `validator_metrics.py`에서 numpy 반환 함수를 `-> Any`로 선언.

**리스크**: 타입 안전성 약화. 단, engine 기존 어댑터(`hf_mobilesam.py` 등)도 동일 패턴이므로 프로젝트 내 일관성은 유지.

**향후**: numpy stubs(`numpy>=1.20` 이상)가 개선되면 구체적 타입으로 전환 가능.

---

## 4. Phase 3 착수 전 확인 — 어댑터 이식 준비 상태

### 4.1 Gemini SDK 직접 호출 패턴 통일 [MEDIUM]

원본 4개 Gemini 모듈의 SDK 사용 패턴을 확인:

| 모듈 | 클라이언트 초기화 | 이미지 전달 | 영상 전달 |
|------|-----------------|------------|----------|
| wan_mode_classifier.py | `genai.Client(api_key=api_key)` | `PILImage.open()` → contents에 직접 | — |
| wan_vision_analyzer.py | 동일 | 동일 | — |
| wan_ai_validator.py | 동일 | `PILImage.open()` 5프레임 추출 | — (프레임 이미지로 전달) |
| wan_post_motion_classifier.py | 동일 | `PILImage.open()` (원본) | `video_bytes` inline / file upload (18MB 기준) |

**주의**: wan_ai_validator.py는 영상을 프레임 이미지로 분해해서 전달, wan_post_motion_classifier.py는 mp4 바이트를 직접 전달. 두 어댑터의 Gemini 호출 방식이 다름.

**확인 필요**: `load(handle: ModelHandle)` 패턴에서 `handle`이 어떤 정보를 전달할지:
- `api_key: str` — 필수
- `model: str` — 필수 (gemini-2.5-flash 등)
- `max_retries: int` — 선택 (기본 3)
- `temperature: float` — 모듈마다 다름 (0.1 ~ 0.5)

→ 이 값들을 ModelHandle에 넣을지 Hydra config에서 어댑터 생성자로 넣을지 결정 필요.

### 4.2 wan_backend.py ComfyUI 부분 — 글로벌 상수 목록 확인 [MEDIUM]

Phase 3에서 `comfyui_animation.py` 어댑터로 이식할 때 Hydra config로 전환해야 할 글로벌 상수:

| 상수 | 원본 줄 | 기본값 | Hydra config 키 |
|------|---------|--------|-----------------|
| `COMFYUI_URL` | 69 | `http://127.0.0.1:8188` | `comfyui.url` |
| `WAN_MODEL` | 70 | `wan2.1-i2v-14b-480p-Q3_K_S.gguf` | `comfyui.wan_model` |
| `CLIP_MODEL` | 71 | `clip_vision_h.safetensors` | `comfyui.clip_model` |
| `VAE_MODEL` | 72 | `wan_2.1_vae.safetensors` | `comfyui.vae_model` |
| `COMFYUI_ROOT` | 77-80 | `~/ComfyUI` | `comfyui.root_dir` |
| `WAN_WORKFLOW_PATH` | 87-94 | `~/ComfyUI/user/default/workflows/...` | `comfyui.workflow_path` |
| `POSITIVE_CLIP_NODE_ID` | 1108 | `None` (자동 감지) | `comfyui.positive_clip_node_id` |
| `NEGATIVE_CLIP_NODE_ID` | 1109 | `None` (자동 감지) | `comfyui.negative_clip_node_id` |
| `MAX_RETRIES` | 66 | `7` | `pipeline.max_retries` (AnimatePipelineConfig에 이미 존재) |
| `ATTEMPT_OFFSET` | 67 | `0` | `pipeline.attempt_offset` (또는 제거) |

### 4.3 wan_bg_remover.py — FormatConversionPort 분리 범위 [LOW]

계획서에서 `_save_apng()`과 `_save_webm()`을 BackgroundRemovalPort에서 분리하여 FormatConversionPort로 이동하기로 결정.

Phase 3에서 구현 시:
- `bg_remover.py`: `remove_background()` → PNG 시퀀스만 생성 (APNG/WebM 생성 코드 제거)
- `lottie_converter.py` 또는 새로운 `format_converter.py`: APNG + WebM + Lottie 변환 통합

원본 `_save_apng()`(줄 199-213)과 `_save_webm()`(줄 215-254)은 각각 30줄 미만으로 간단.

---

## 5. 확인 사항 요약

| # | 항목 | 심각도 | Phase | 상태 | 조치 |
|---|------|--------|-------|------|------|
| 1 | ghosting/background_color_change 수치 검증 존재 확인 | — | 2 | ✅ RESOLVED | 이전 리뷰 지적 정정 완료 |
| 2 | domain/__init__.py re-export 18개 완전성 | LOW | 1 | ⬜ Phase 3에서 자동 확인 | import 시 검증 |
| 3 | ports/__init__.py re-export 10개 완전성 | LOW | 1 | ⬜ Phase 3에서 자동 확인 | import 시 검증 |
| 4 | 검증 지표 "8개" 표기 → "9개" 정정 | LOW | 2 | ⬜ 보고서 표기만 수정 | 코드 영향 없음 |
| 5 | check_* bool 플래그 제거 영향 | LOW | 2 | ✅ 확인 완료 | 영향 없음 |
| 6 | _calc_center_drift 미이식 | LOW | 2 | ✅ 확인 완료 | 데드 코드 |
| 7 | preprocess_image() 미이식 | LOW | 2 | ✅ 확인 완료 | 데드 코드 |
| 8 | numpy Any 반환 타입 | LOW | 2 | ✅ 확인 완료 | engine 기존 패턴 일관 |
| 9 | Gemini 어댑터 load(handle) 파라미터 설계 | MEDIUM | 3 | ⬜ Phase 3 착수 시 결정 | 4.1 참조 |
| 10 | ComfyUI 글로벌 상수 10개 → Hydra config 전환 | MEDIUM | 3 | ⬜ Phase 3 착수 시 적용 | 4.2 참조 |
| 11 | bg_remover APNG/WebM → FormatConversionPort 분리 | LOW | 3 | ⬜ Phase 3에서 구현 | 4.3 참조 |

**차단 이슈: 0건. Phase 3 착수 가능.**
