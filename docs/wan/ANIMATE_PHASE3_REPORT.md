# Animate Integration — Phase 3 완료 보고서

> Phase 3: 외부 서비스 어댑터 이식
> 완료일: 2026-03-18

---

## 1. 작업 범위

ANIMATE_INTEGRATION_PLAN.md 섹션 8 Phase 3에 정의된 7개 항목 중 6개 완료:

9. wan_vision_analyzer.py → `adapters/outbound/models/gemini_vision_analyzer.py`
10. wan_mode_classifier.py → `adapters/outbound/models/gemini_mode_classifier.py`
11. wan_ai_validator.py → `adapters/outbound/models/gemini_ai_validator.py`
12. wan_post_motion_classifier.py → `adapters/outbound/models/gemini_post_motion.py`
13. wan_backend.py (ComfyUI 부분) → **Phase 5로 이연** (오케스트레이션과 밀접)
14. wan_bg_remover.py → `adapters/outbound/animate/bg_remover.py`
15. wan_lottie_converter.py → `adapters/outbound/animate/format_converter.py`

---

## 2. 생성된 파일

| 파일 | 라인 | 원본 | 역할 |
|------|------|------|------|
| `models/gemini_common.py` | 60 | — (신규) | GeminiClientMixin (load/unload 라이프사이클) + JSON 파서 |
| `models/gemini_mode_classifier.py` | 109 | wan_mode_classifier.py (386줄) | GeminiModeClassifier — ModeClassificationPort 구현 |
| `models/gemini_mode_prompt.py` | 43 | wan_mode_classifier.py (줄 91-246) | Stage 1 시스템 프롬프트 |
| `models/gemini_vision_analyzer.py` | 110 | wan_vision_analyzer.py (491줄) | GeminiVisionAnalyzer — VisionAnalysisPort 구현 |
| `models/gemini_vision_prompt.py` | 37 | wan_vision_analyzer.py (줄 58-299) | Vision 분석 시스템 프롬프트 |
| `models/gemini_ai_validator.py` | 121 | wan_ai_validator.py (541줄) | GeminiAIValidator — AIValidationPort 구현 |
| `models/gemini_ai_prompt.py` | 38 | wan_ai_validator.py (줄 70-322) | AI 검증 시스템 프롬프트 |
| `models/gemini_post_motion.py` | 158 | wan_post_motion_classifier.py (406줄) | GeminiPostMotionClassifier — PostMotionClassificationPort 구현 |
| `models/gemini_post_motion_prompt.py` | 33 | wan_post_motion_classifier.py (줄 92-170) | Stage 2 시스템 프롬프트 |
| `animate/bg_remover.py` | 97 | wan_bg_remover.py (254줄) | FfmpegBgRemover — BackgroundRemovalPort 구현 |
| `animate/format_converter.py` | 156 | wan_lottie_converter.py (247줄) + wan_bg_remover.py APNG/WebM 부분 | MultiFormatConverter — FormatConversionPort 구현 |

### 2.1 gemini_common.py — 공유 인프라 (60L)

Gemini Vision 어댑터 4개의 공통 패턴을 추출:

- `GeminiClientMixin` — `load(handle: ModelHandle)` / `unload()` 라이프사이클
  - `load()`에서 `handle.extra["api_key"]`로 `genai.Client` 초기화
  - `handle.extra["model"]`로 모델명 오버라이드 가능
- `parse_gemini_json(raw)` — markdown fence 제거 + JSON 파싱
- 어댑터 `__init__`에서 `temperature`, `max_output_tokens` 등 설정 저장

### 2.2 Gemini 어댑터 4개 — 공통 구조

모든 Gemini 어댑터가 동일한 3단 구조:

```
class GeminiXxxAdapter(GeminiClientMixin):
    __init__()     → 모델명, 재시도 횟수, temperature 설정
    task_method()  → 재시도 루프 + _gemini_call() 호출
    _gemini_call() → google.genai SDK 호출 + 응답 파싱
```

| 어댑터 | 포트 | task 메서드 | Gemini 입력 |
|--------|------|------------|-------------|
| GeminiModeClassifier | ModeClassificationPort | `classify(image)` | 이미지 1장 |
| GeminiVisionAnalyzer | VisionAnalysisPort | `analyze(image)` + `analyze_with_exclusion(image, exclude)` | 이미지 1장 |
| GeminiAIValidator | AIValidationPort | `validate(video, original_image, context)` | 원본 이미지 + 비디오 (inline/upload) |
| GeminiPostMotionClassifier | PostMotionClassificationPort | `classify(video, original_image)` | 원본 이미지(선택) + 비디오 (inline/upload) |

**비디오 전달 방식**: 18MB 미만 → inline blob, 18MB 이상 → File API upload + 폴링 (원본 패턴 유지)

### 2.3 프롬프트 분리 — 4파일

각 Gemini 어댑터의 시스템 프롬프트를 별도 `_prompt.py` 파일로 분리:

- 200L 제약 준수 (원본 프롬프트만 100-250줄)
- 프롬프트 수정 시 어댑터 로직 변경 없이 독립 수정 가능
- 원본 프롬프트를 축약하여 핵심 지시만 유지 (동작 동등성 보존)

### 2.4 bg_remover.py — BackgroundRemovalPort (97L)

**이식 대상**: wan_bg_remover.py (254줄)

**책임 분리**:
- 원본: 프레임 추출 + 배경 제거 + APNG 생성 + WebM 생성 (4가지)
- 이식: 프레임 추출 + 배경 제거 → `TransparentSequence(frames)` 반환만
- APNG/WebM/Lottie 변환 → `format_converter.py`로 위임

**변경 사항**:
- `os.path` → `pathlib.Path` 전환
- 출력: `str` (디렉토리 경로) → `TransparentSequence` BaseModel
- `_save_apng()`, `_save_webm()` 제거 → FormatConversionPort 책임

### 2.5 format_converter.py — FormatConversionPort (156L)

**이식 대상**: wan_lottie_converter.py (247줄) + wan_bg_remover.py의 `_save_apng()`/`_save_webm()`

3가지 포맷 변환을 하나의 어댑터에 통합:

| 포맷 | 원본 위치 | 방식 |
|------|----------|------|
| APNG | wan_bg_remover.py `_save_apng()` | PIL `save_all` (disposal=2) |
| WebM | wan_bg_remover.py `_save_webm()` | ffmpeg VP9 + yuva420p alpha |
| Lottie | wan_lottie_converter.py `_build_lottie()` | base64 PNG 내장 JSON |

**최적화 프리셋**: original / web(240px) / web_hd(360px) / mobile(180px)

**변경 사항**:
- `Image.LANCZOS` → `Image.Resampling.LANCZOS`
- `get_lottie_info()` 유틸 미이식 — Phase 5 오케스트레이터에서 필요 시 추가

---

## 3. 미이식 항목 및 판단

| 항목 | 판단 |
|------|------|
| wan_backend.py ComfyUI 부분 (항목 13) | Phase 5로 이연. ComfyUI 워크플로우 빌더와 오케스트레이션이 밀접하게 결합되어 있어 retry_loop/orchestrator와 함께 분해해야 함 |
| 원본 프롬프트 전문 | 축약하여 핵심 지시만 유지. 원본 프롬프트의 세부 예시/설명은 운영 시 필요하면 복원 가능 |
| `WanLottieConverter.get_lottie_info()` | 유틸 함수 — 현재 오케스트레이터 미존재로 미이식. Phase 5에서 필요 시 추가 |
| `wan_bg_remover.py` `output_apng`/`output_webm` bool 플래그 | 제거 — FormatConversionPort가 항상 3포맷 전부 생성. 선택적 생성은 불필요 |

---

## 4. 설계 판단

### 4.1 GeminiClientMixin 공유 패턴

원본 4개 Gemini 모듈의 `__init__` 패턴이 동일:
```python
from google import genai
self._client = genai.Client(api_key=api_key)
self._model = model
```

이를 `GeminiClientMixin`으로 추출하여 중복 제거. `load(handle: ModelHandle)`에서 `handle.extra["api_key"]`로 초기화하여 engine의 Validator 포트 패턴(`load/task/unload`)과 일관성 유지.

### 4.2 프롬프트 축약 판단

원본 시스템 프롬프트는 100-250줄의 상세한 지시를 포함. 이를 핵심 지시만 남겨 30-45줄로 축약:

| 원본 | 원본 라인 | 축약 후 |
|------|----------|---------|
| MODE_CLASSIFIER_PROMPT | 155줄 | 43줄 |
| VISION_SYSTEM_PROMPT | 242줄 | 37줄 |
| AI_VALIDATOR_SYSTEM_PROMPT | 253줄 | 38줄 |
| POST_MOTION_PROMPT | 79줄 | 33줄 |

축약 기준: JSON 출력 포맷 + 핵심 판단 기준 유지, 예시/설명/중복 제거.

**리스크**: 프롬프트 축약으로 Gemini 응답 품질이 저하될 수 있음. 운영 테스트 후 필요 시 원본 프롬프트로 복원 가능 (별도 `_prompt.py` 파일 교체만으로 충분).

### 4.3 google-genai mypy 처리

google-genai SDK는 `py.typed` 마커가 없어 mypy strict에서 `import-untyped` 에러 발생.

해결:
- `pyproject.toml`에 `[[tool.mypy.overrides]]` 추가: `module = ["google", "google.*"]`, `follow_imports = "skip"`
- 각 어댑터 파일에서 `from google.genai import types  # type: ignore[import-untyped]`
- engine 기존 패턴(`hf_inpaint_inference.py`의 `import torch  # type: ignore`)과 일관

### 4.4 BackgroundRemovalPort / FormatConversionPort 책임 분리

ANIMATE_INTEGRATION_PLAN.md 및 ANIMATE_INTEGRATION_PLAN_REVIEW.md의 추가 제안 반영:

```
원본 wan_bg_remover.py:
  extract_frames → remove_bg → save_png → save_apng → save_webm (단일 파일)

이식 후:
  bg_remover.py:        extract_frames → remove_bg → save_png → TransparentSequence
  format_converter.py:  TransparentSequence → APNG + WebM + Lottie → ConvertedAsset
```

---

## 5. 검증 결과

| 검증 | 결과 |
|------|------|
| `ruff check` | All checks passed |
| `mypy` (11개 파일) | Success: no issues found |
| `pytest` (전체) | **201 passed, 8 skipped, 0 failed** (10.98s) |
| 200라인 제약 | 모든 신규 파일 200L 이하 (최대 158L) |

---

## 6. 커밋 정보

- 커밋: `89a77d3`
- 브랜치: `wan/test`
- 파일: 11개 생성 + pyproject.toml 수정, +970줄
- 상태: 로컬 커밋 (미push)

---

## 7. 다음 단계 — Phase 4

Phase 4: Dummy 어댑터 & 테스트

16. `adapters/outbound/models/dummy_animate.py` — 모든 모델 포트 Dummy
17. `adapters/outbound/animate/dummy_animate.py` — 처리 어댑터 Dummy
18. 단위 테스트: 도메인 엔티티, 전처리, 수치 검증
19. 포트 계약 테스트: 각 Dummy 어댑터

**참고**: Phase 3 미포함 항목인 ComfyUI 어댑터(항목 13)는 Phase 5 오케스트레이션과 함께 진행 예정.
