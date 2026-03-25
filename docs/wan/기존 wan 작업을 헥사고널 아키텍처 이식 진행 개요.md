# Animate Pipeline Integration — Phase 1~6 통합 요약

> sprite_gen → engine 헥사고널 아키텍처 이식 프로젝트
> 작업 기간: 2026-03-18 ~ 03-19
> 브랜치: wan/test

---

## 1. 프로젝트 개요

`/home/snake2/anim_pipeline/image_pipeline/sprite_gen/` (6,745줄, 12개 파일)의
AI 기반 스프라이트 애니메이션 생성 파이프라인을
`/home/snake2/engine/`의 헥사고널 아키텍처(Ports & Adapters)에 이식.

**원본 파이프라인 흐름**:

```
입력 이미지
  → Stage 1: Mode 분류 (KEYFRAME_ONLY / MOTION_NEEDED)
  → Vision 분석 (Gemini → 모션 파라미터)
  → WAN I2V 생성 (ComfyUI, 최대 7회 재시도)
  → 수치 검증 (9개 품질 지표) + AI 검증 (Gemini Vision)
  → Stage 2: 후처리 분류 (키프레임 트래블)
  → 배경 제거 → 포맷 변환 (APNG / WebM / Lottie)
```

---

## 2. Phase별 진행

### Phase 1 — 도메인 & 포트 (`4bf038f`)

- Enum 4개: `ProcessingMode`, `FacingDirection`, `MotionTravelType`, `TravelDirection`
- Pydantic BaseModel 엔티티 14개 (분류/분석/검증/결과/키프레임)
- Protocol 포트 인터페이스 10개
- `AnimatePipelineConfig` 설정 스키마
- 200L 초과 → `animate.py`(146L) + `animate_keyframe.py`(66L) 분할

### Phase 2 — 순수 로직 이식 (`d73e6d3`)

| 원본 | 이식 파일 | 줄 |
|------|----------|-----|
| wan_backend.py 전처리 | `preprocessing.py` | 114 |
| wan_mask_generator.py | `mask_generator.py` | 58 |
| wan_keyframe_generator.py (512줄) | `keyframe_generator.py` + `keyframe_travel.py` + `keyframe_physics.py` | 257 |
| wan_validator.py (708줄) | `numerical_validator.py` + `validator_metrics.py` + `frame_extraction.py` | 351 |

**수치 검증 9개 지표**: no_motion, too_slow, too_fast, repeated_motion, frame_escape, no_return_to_origin, center_drift, ghosting, background_color_change

### Phase 3 — 외부 서비스 어댑터 (`89a77d3`)

| 원본 | 이식 파일 | 역할 |
|------|----------|------|
| wan_mode_classifier.py | `gemini_mode_classifier.py` + `_prompt.py` | Stage 1 분류 |
| wan_vision_analyzer.py | `gemini_vision_analyzer.py` + `_prompt.py` | Vision 분석 |
| wan_ai_validator.py | `gemini_ai_validator.py` + `_prompt.py` | AI 검증 |
| wan_post_motion_classifier.py | `gemini_post_motion.py` + `_prompt.py` | Stage 2 분류 |
| wan_bg_remover.py | `bg_remover.py` | 배경 제거 |
| wan_lottie_converter.py | `format_converter.py` | APNG/WebM/Lottie 통합 변환 |

- `GeminiClientMixin` 공유 인프라 (load/unload 라이프사이클)
- 비디오 전달: 18MB 미만 inline blob / 18MB 이상 File API upload
- `BackgroundRemovalPort` / `FormatConversionPort` 책임 분리 완료

### Phase 4 — Dummy 어댑터 & 테스트 (`010e570`)

- 모델 포트 Dummy 5개 (`dummy_animate.py` 133L)
- 처리 어댑터 Dummy 5개 (`dummy_animate.py` 89L)
- 도메인 엔티티 단위 테스트 19건 + 포트 계약 테스트 11건
- 성공 경로 우선 (orchestrator 통합 테스트 대비)

### Phase 5 — 오케스트레이션 & 부트스트랩 (`e850059`)

| 파일 | 줄 | 역할 |
|------|-----|------|
| `orchestrator.py` | 189 | 전체 파이프라인 조율 (포트 인터페이스만 참조) |
| `retry_loop.py` | 186 | 재시도 전략 — 헬퍼 5개로 원본 3곳 중복 제거 |
| `retry_state.py` | 65 | 루프 상태 + 상수 (bg_type별 중국어 프롬프트 포함) |
| `factory.py` (수정) | 185 | `build_animate_context()` Hydra instantiate 팩토리 |

**원본 576줄 → 440줄 (3파일)로 재구성**, 중복 코드 2건 제거:
- 액션 전환 로직 (3곳 → `_switch_action()` 1개)
- AI 조정 적용 (2곳 → `_apply_adj()` 1개)

**설계 결정**:
- 첫 성공 시 즉시 반환 (원본은 MAX_RETRIES 전부 소진)
- Stage 2 자동 호출 (원본은 대시보드 수동)
- `_ValidationStats` 파일 이력 → 세션 내 `Counter` 기반 대체

### Phase 6 — Flow 연결 & 통합 테스트 (`46439f7`)

- `animate_pipeline()` subflow 함수 추가 (기존 `animate_stub()` 보존)
- Hydra `animate_pipeline.yaml` 설정 (`-o flows/animate=animate_pipeline`으로 활성화)
- Flow 레벨 통합 테스트 2건 (missing image_path + full flow with dummies)

---

## 3. 추가 수정 (Phase 완료 후)

### 프롬프트 원본 복원 (HIGH 해소)

4개 Gemini 프롬프트가 72-85% 축약된 상태 → 원본 전문 복원:

| 파일 | 축약 → 복원 | 분할 |
|------|-----------|------|
| `gemini_mode_prompt.py` | 43줄 → 190줄 | + `gemini_mode_fallback.py` (110줄) |
| `gemini_vision_prompt.py` | 37줄 → 265줄 | + `_parts.py` (118줄) + `_steps.py` (138줄) |
| `gemini_ai_prompt.py` | 38줄 → 275줄 | + `_criteria.py` (176줄) + `_fixes.py` (90줄) |
| `gemini_post_motion_prompt.py` | 33줄 → 85줄 | 단일 파일 |

### mode_classifier 강화 (`46b77da`)

- 3단계 JSON 복구 (정상 → 따옴표/중괄호 수리 → 키워드 추출)
- `has_deformable_parts` 누락 시 `processing_mode`에서 추론
- 강체 패턴 감지: 영문 18개 + 중국어 8개 = 26개 패턴, NO_DEFORM 11개

### Lottie Baker (`40ec18c`)

- `lottie_baker.py` (45줄) — `bake_keyframes()` 진입점
- `lottie_baker_transform.py` (83줄) — precomp 래퍼 변환

---

## 4. 아키텍처 구조

```
src/discoverex/
├── domain/
│   ├── animate.py                    # Enum 4 + BaseModel 10
│   └── animate_keyframe.py           # 키프레임 3 + 결과 3
├── application/
│   ├── ports/animate.py              # Protocol 10개
│   └── use_cases/animate/
│       ├── orchestrator.py           # 전체 파이프라인 조율
│       ├── retry_loop.py             # 재시도 전략
│       ├── retry_state.py            # 루프 상태 + 상수
│       └── preprocessing.py          # 이미지 전처리
├── adapters/outbound/
│   ├── models/
│   │   ├── gemini_common.py          # 공유 Mixin
│   │   ├── gemini_mode_classifier.py # Stage 1
│   │   ├── gemini_mode_fallback.py   # Stage 1 fallback 패턴 감지
│   │   ├── gemini_vision_analyzer.py # Vision 분석
│   │   ├── gemini_ai_validator.py    # AI 검증
│   │   ├── gemini_post_motion.py     # Stage 2
│   │   ├── gemini_*_prompt*.py       # 프롬프트 (원본 전문, 파일 분할)
│   │   └── dummy_animate.py          # 모델 Dummy 5개
│   └── animate/
│       ├── numerical_validator.py    # 9개 수치 검증
│       ├── validator_metrics.py      # 지표 계산 함수
│       ├── frame_extraction.py       # ffmpeg 프레임 추출
│       ├── bg_remover.py             # 배경 제거
│       ├── format_converter.py       # APNG/WebM/Lottie
│       ├── lottie_baker.py           # 키프레임 베이크
│       ├── lottie_baker_transform.py # precomp 변환
│       ├── mask_generator.py         # 바이너리 마스크
│       ├── keyframe_generator.py     # CSS 키프레임
│       ├── keyframe_travel.py        # launch/float/hop
│       ├── keyframe_physics.py       # damped sin/cos
│       └── dummy_animate.py          # 처리 Dummy 5개
├── config/animate_schema.py          # 설정 스키마
├── bootstrap/factory.py              # build_animate_context()
└── flows/subflows.py                 # animate_pipeline()

conf/
├── models/*/dummy.yaml × 5
├── animate_adapters/*/dummy.yaml × 5
└── flows/animate/
    ├── stub.yaml
    ├── replay_eval.yaml
    └── animate_pipeline.yaml

tests/
├── test_animate_domain.py            # 19건
├── test_animate_ports_contract.py    # 11건
├── test_animate_orchestrator.py      # 1건
└── test_animate_flow.py              # 2건
```

---

## 5. 원본 파일 이식 매핑

| sprite_gen 원본 (줄) | engine 이식 위치 | 상태 |
|---------------------|-----------------|------|
| wan_mode_classifier.py (386) | gemini_mode_classifier.py + fallback + prompt | ✅ |
| wan_vision_analyzer.py (491) | gemini_vision_analyzer.py + prompt (3파일) | ✅ |
| wan_ai_validator.py (541) | gemini_ai_validator.py + prompt (3파일) | ✅ |
| wan_post_motion_classifier.py (406) | gemini_post_motion.py + prompt | ✅ |
| wan_validator.py (708) | numerical_validator.py + metrics + extraction | ✅ |
| wan_keyframe_generator.py (512) | keyframe_generator.py + travel + physics | ✅ |
| wan_mask_generator.py (104) | mask_generator.py | ✅ |
| wan_bg_remover.py (254) | bg_remover.py + format_converter.py | ✅ |
| wan_lottie_converter.py (247) | format_converter.py (통합) | ✅ |
| wan_lottie_baker.py (208) | lottie_baker.py + transform | ✅ |
| wan_backend.py 전처리 (164) | preprocessing.py | ✅ |
| wan_backend.py 오케스트레이션 (576) | orchestrator.py + retry_loop.py + retry_state.py | ✅ |
| wan_backend.py ComfyUI (843) | 별도 세션에서 구현 (comfyui_*.py 3파일) | ✅ |
| wan_server.py (581) | engine 외부 (REST API) | ❌ 제외 |
| wan_dashboard.html | engine 외부 (웹 UI) | ❌ 제외 |

**이식률**: 13/15 모듈 완료 (REST API·대시보드 제외)

---

## 6. 호환성 검증에서 발견된 주요 이슈 및 해결

| 이슈 | 심각도 | 해결 |
|------|--------|------|
| `VisionAnalysisPort`에 `analyze_with_exclusion` 미반영 | MEDIUM | 포트 + Dummy에 메서드 추가 |
| `KeyframeConfig` DTO 미정의 | MEDIUM | domain에 추가 |
| `AIValidationContext` DTO 미정의 | MEDIUM | domain에 추가 |
| ComfyUI 글로벌 상수 10개 | MEDIUM | Hydra config로 전환 (별도 세션) |
| `_ValidationStats` 이력 기반 negative 강화 | MEDIUM | 세션 내 Counter로 대체, 이후 파일 기반 복원 |
| 프롬프트 72-85% 축약 | **HIGH** | 원본 전문 복원 + 200L 준수 위해 파일 분할 |
| RIGID BODY RULE 누락 | **HIGH** | `gemini_mode_fallback.py` 신규, 26개 패턴 복원 |
| soft_pass Pydantic immutable | MEDIUM | 새 인스턴스 생성 패턴 확인 (문제 없음) |

---

## 7. 전체 수치

| 항목 | 수치 |
|------|------|
| 커밋 | 20개 (Phase 1~6) |
| 코드 파일 (신규/수정) | 53개, +4,108줄 |
| 문서 파일 | 21개 (현재 본 문서로 통합) |
| 테스트 | **234 passed, 8 skipped, 0 failed** |
| 신규 테스트 | 33건 (4개 파일) |
| 200L 제약 위반 | 0건 |
| mypy strict 에러 | 0건 |
| ruff 에러 | 0건 |

---

## 8. 커밋 이력 (시간순)

| # | 커밋 | 유형 | Phase | 내용 |
|---|------|------|-------|------|
| 1 | `4bf038f` | feat | 1 | 도메인 + 포트 + 설정 |
| 2 | `d73e6d3` | feat | 2 | 순수 로직 이식 10파일 |
| 3 | `a61ea21` | docs | 2 | Phase 2 보고서 |
| 4 | `cd3d6df` | docs | 2 | 검증 지표 8→9 정정 |
| 5 | `89a77d3` | feat | 3 | Gemini 4 + bg/format 어댑터 |
| 6 | `af45636` | docs | 3 | Phase 3 보고서 |
| 7 | `364b7dd` | docs | 3 | Phase 3 리뷰 |
| 8 | `010e570` | feat | 4 | Dummy 10개 + 테스트 30건 |
| 9 | `48f518a` | docs | 4 | Phase 4 보고서 |
| 10 | `15ae983` | docs | 4 | Phase 4 체크리스트 |
| 11 | `e850059` | feat | 5 | 오케스트레이터 + 부트스트랩 |
| 12 | `d00a34d` | docs | 5 | Phase 5 보고서 |
| 13 | `46b77da` | fix | — | mode_classifier 복구 + bg 프롬프트 |
| 14 | `94e7f80` | docs | — | 체크리스트 결과 + 미해결 종합 |
| 15 | `40ec18c` | feat | — | 프롬프트 원본 복원 4개 + Lottie Baker |
| 16 | `299111d` | docs | — | 최종 진행 현황 |
| 17 | `b31ae34` | docs | — | sprite_gen 수정 이력 보완 |
| 18 | `68fcb69` | docs | — | 보완 적용 결과 |
| 19 | `46439f7` | feat | 6 | Flow 연결 + 통합 테스트 |
| 20 | `a3a6082` | docs | 6 | Phase 6 보고서 |

