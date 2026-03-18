# Animate Integration — 최종 진행 현황

> 작성일: 2026-03-18
> 브랜치: wan/test

---

## 1. Phase 완료 현황

| Phase | 내용 | 상태 | 커밋 |
|-------|------|------|------|
| Phase 1 | 도메인 엔티티 + 포트 인터페이스 + 설정 스키마 | ✅ 완료 | `4bf038f` |
| Phase 2 | 수치 검증 + 순수 로직 이식 (전처리/마스크/키프레임/검증) | ✅ 완료 | `d73e6d3` |
| Phase 3 | 외부 서비스 어댑터 (Gemini 4개 + bg_remover + format_converter) | ✅ 완료 | `89a77d3` |
| Phase 4 | Dummy 어댑터 10개 + 테스트 30건 | ✅ 완료 | `010e570` |
| Phase 5 | 오케스트레이터 + 재시도 루프 + 부트스트랩 + Hydra 설정 | ✅ 완료 | `e850059` |
| Phase 6 | Flow 연결 + E2E | ⬜ 미착수 | — |

---

## 2. 추가 반영 완료 항목

| 항목 | 커밋 | 내용 |
|------|------|------|
| 검증 지표 표기 정정 | `cd3d6df` | 8개 → 9개 (ghosting/bg_color_change 포함) |
| Phase 5 체크리스트 반영 | `46b77da` | mode_classifier 3단계 복구, bg 프롬프트 원본 복원 |
| 프롬프트 원본 복원 | `40ec18c` | 4개 `_prompt.py` 원본 전문 복원 (HIGH 해소) |
| Lottie Baker | `40ec18c` | lottie_baker.py + lottie_baker_transform.py 신규 |

---

## 3. 전체 수치 요약

| 항목 | 수치 |
|------|------|
| 신규 파일 | 48개 |
| 신규 코드 | +5,700줄 이상 |
| 테스트 | **232 passed, 8 skipped, 0 failed** |
| 200L 제약 위반 | 0건 |
| mypy strict 에러 | 0건 |
| ruff 에러 | 0건 |

---

## 4. 파일 목록 전수

### 4.1 도메인 (Phase 1)

| 파일 | 라인 | 역할 |
|------|------|------|
| `src/discoverex/domain/animate.py` | 146 | Enum 4개 + 분류/분석/검증 BaseModel 10개 |
| `src/discoverex/domain/animate_keyframe.py` | 66 | 키프레임 구조 3개 + 생성 결과 3개 |

### 4.2 포트 인터페이스 (Phase 1)

| 파일 | 라인 | 역할 |
|------|------|------|
| `src/discoverex/application/ports/animate.py` | 152 | Protocol 10개 |

### 4.3 설정 스키마 (Phase 1)

| 파일 | 라인 | 역할 |
|------|------|------|
| `src/discoverex/config/animate_schema.py` | 44 | AnimatePipelineConfig + 하위 설정 |

### 4.4 순수 로직 어댑터 (Phase 2)

| 파일 | 라인 | 원본 | 역할 |
|------|------|------|------|
| `adapters/outbound/animate/mask_generator.py` | 58 | wan_mask_generator.py | PilMaskGenerator |
| `adapters/outbound/animate/keyframe_generator.py` | 144 | wan_keyframe_generator.py | PilKeyframeGenerator |
| `adapters/outbound/animate/keyframe_travel.py` | 98 | wan_keyframe_generator.py | launch/float/parabolic/hop |
| `adapters/outbound/animate/keyframe_physics.py` | 15 | wan_keyframe_generator.py | damped_sin/cos |
| `adapters/outbound/animate/numerical_validator.py` | 127 | wan_validator.py | NumericalAnimationValidator |
| `adapters/outbound/animate/validator_metrics.py` | 166 | wan_validator.py | 9개 검증 지표 함수 |
| `adapters/outbound/animate/frame_extraction.py` | 58 | wan_validator.py | ffmpeg 프레임 추출 |

### 4.5 전처리 (Phase 2)

| 파일 | 라인 | 원본 | 역할 |
|------|------|------|------|
| `application/use_cases/animate/preprocessing.py` | 114 | wan_backend.py | white_anchor + preprocess_image_simple |

### 4.6 Gemini Vision 어댑터 (Phase 3)

| 파일 | 라인 | 원본 | 역할 |
|------|------|------|------|
| `models/gemini_common.py` | 60 | — | GeminiClientMixin + JSON 파서 |
| `models/gemini_mode_classifier.py` | 152 | wan_mode_classifier.py | ModeClassificationPort + 3단계 복구 |
| `models/gemini_mode_prompt.py` | 162 | wan_mode_classifier.py | Stage 1 프롬프트 (원본 전문) |
| `models/gemini_vision_analyzer.py` | 110 | wan_vision_analyzer.py | VisionAnalysisPort |
| `models/gemini_vision_prompt.py` | 133 | wan_vision_analyzer.py | Vision 프롬프트 (PART1+PART2) |
| `models/gemini_ai_validator.py` | 121 | wan_ai_validator.py | AIValidationPort |
| `models/gemini_ai_prompt.py` | 124 | wan_ai_validator.py | AI 검증 프롬프트 (PART1+PART2) |
| `models/gemini_post_motion.py` | 158 | wan_post_motion_classifier.py | PostMotionClassificationPort |
| `models/gemini_post_motion_prompt.py` | 85 | wan_post_motion_classifier.py | Stage 2 프롬프트 (원본 전문) |

### 4.7 영상/포맷 어댑터 (Phase 3)

| 파일 | 라인 | 원본 | 역할 |
|------|------|------|------|
| `adapters/outbound/animate/bg_remover.py` | 97 | wan_bg_remover.py | BackgroundRemovalPort |
| `adapters/outbound/animate/format_converter.py` | 156 | wan_lottie_converter.py + bg_remover APNG/WebM | FormatConversionPort |

### 4.8 Lottie Baker (추가 반영)

| 파일 | 라인 | 원본 | 역할 |
|------|------|------|------|
| `adapters/outbound/animate/lottie_baker.py` | 45 | wan_lottie_baker.py | bake_keyframes() 진입점 |
| `adapters/outbound/animate/lottie_baker_transform.py` | 83 | wan_lottie_baker.py | precomp 래퍼 변환 로직 |

### 4.9 Dummy 어댑터 (Phase 4)

| 파일 | 라인 | 역할 |
|------|------|------|
| `models/dummy_animate.py` | 133 | 모델 포트 Dummy 5개 |
| `adapters/outbound/animate/dummy_animate.py` | 89 | 처리 어댑터 Dummy 5개 |

### 4.10 오케스트레이션 (Phase 5)

| 파일 | 라인 | 역할 |
|------|------|------|
| `application/use_cases/animate/orchestrator.py` | 189 | AnimateOrchestrator |
| `application/use_cases/animate/retry_loop.py` | 186 | RetryLoop (재시도 전략) |
| `application/use_cases/animate/retry_state.py` | 71 | LoopState + 상수 |

### 4.11 부트스트랩 + Hydra 설정 (Phase 5)

| 파일 | 역할 |
|------|------|
| `bootstrap/factory.py` (수정) | build_animate_context() 추가 |
| `conf/models/*/dummy.yaml` × 5 | 모델 포트 Hydra 설정 |
| `conf/animate_adapters/*/dummy.yaml` × 5 | 처리 어댑터 Hydra 설정 |
| `conf/flows/animate/pipeline.yaml` | 전체 어댑터 조합 |

### 4.12 테스트 (Phase 4-5)

| 파일 | 라인 | 테스트 수 |
|------|------|----------|
| `tests/test_animate_domain.py` | 166 | 19건 (도메인 엔티티) |
| `tests/test_animate_ports_contract.py` | 163 | 11건 (포트 계약) |
| `tests/test_animate_orchestrator.py` | 80 | 1건 (통합 E2E) |

### 4.13 문서

| 파일 | 내용 |
|------|------|
| `ANIMATE_INTEGRATION_PLAN.md` | 통합 계획서 (전체 10개 섹션) |
| `ANIMATE_INTEGRATION_PLAN_REVIEW.md` | 계획서 리뷰 수정 지시 7건 |
| `ANIMATE_COMPATIBILITY_VERIFICATION.md` | 코드 레벨 호환성 검증 |
| `ANIMATE_PHASE1_REPORT.md` | Phase 1 완료 보고서 |
| `ANIMATE_PHASE2_REPORT.md` | Phase 2 완료 보고서 |
| `ANIMATE_PHASE3_REPORT.md` | Phase 3 완료 보고서 |
| `ANIMATE_PHASE3_REVIEW.md` | Phase 3 리뷰 9건 |
| `ANIMATE_PHASE4_REPORT.md` | Phase 4 완료 보고서 |
| `ANIMATE_PHASE1_2_CHECKLIST.md` | Phase 1-2 체크리스트 |
| `ANIMATE_PHASE4_CHECKLIST.md` | Phase 4 체크리스트 |
| `ANIMATE_PHASE5_REPORT.md` | Phase 5 완료 보고서 |
| `ANIMATE_PHASE5_CHECKLIST.md` | Phase 5 체크리스트 |
| `ANIMATE_PHASE5_CHECKLIST_RESULT.md` | Phase 5 체크리스트 반영 결과 |
| `ANIMATE_REMAINING_ISSUES.md` | 미해결 항목 종합 |
| `ANIMATE_LOTTIE_BAKER_AND_REMAINING.md` | Lottie Baker + 조치 시점 |

---

## 5. 미해결 항목 (Phase 6에서 처리)

| # | 항목 | 심각도 | 조치 시점 |
|---|------|--------|----------|
| 1 | ComfyUI 어댑터 구현 (~843줄, 5파일 분할 예상) | LOW | E2E 스모크 테스트 시 |
| 2 | flows/subflows.py animate_stub 교체 | LOW | Phase 6 항목 25 |
| 3 | 전처리 단위 테스트 추가 (PIL+scipy) | LOW | Phase 6 테스트 보강 |
| 4 | DummyFormatConverter 빈 경로 개선 | LOW | 필요 시 |

**HIGH 0건, MEDIUM 0건** — 차단 이슈 없음.

---

## 6. 원본 파일 이식 매핑

| sprite_gen 원본 | engine 이식 위치 | 상태 |
|----------------|-----------------|------|
| wan_mode_classifier.py (386줄) | gemini_mode_classifier.py + gemini_mode_prompt.py | ✅ |
| wan_vision_analyzer.py (491줄) | gemini_vision_analyzer.py + gemini_vision_prompt.py | ✅ |
| wan_ai_validator.py (541줄) | gemini_ai_validator.py + gemini_ai_prompt.py | ✅ |
| wan_post_motion_classifier.py (406줄) | gemini_post_motion.py + gemini_post_motion_prompt.py | ✅ |
| wan_validator.py (708줄) | numerical_validator.py + validator_metrics.py + frame_extraction.py | ✅ |
| wan_keyframe_generator.py (512줄) | keyframe_generator.py + keyframe_travel.py + keyframe_physics.py | ✅ |
| wan_mask_generator.py (104줄) | mask_generator.py | ✅ |
| wan_bg_remover.py (254줄) | bg_remover.py + format_converter.py | ✅ |
| wan_lottie_converter.py (247줄) | format_converter.py (통합) | ✅ |
| wan_lottie_baker.py (208줄) | lottie_baker.py + lottie_baker_transform.py | ✅ |
| wan_backend.py 전처리 (164줄) | preprocessing.py | ✅ |
| wan_backend.py 오케스트레이션 (576줄) | orchestrator.py + retry_loop.py + retry_state.py | ✅ |
| wan_backend.py ComfyUI (843줄) | — | ⬜ Phase 6 |
| wan_server.py (581줄) | — | ❌ 제외 (REST API) |
| wan_dashboard.html | — | ❌ 제외 (웹 UI) |
