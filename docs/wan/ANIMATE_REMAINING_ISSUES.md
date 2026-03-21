# Animate Integration — 미해결 항목 종합

> Phase 1-5 완료 후 남은 미해결 항목 전수
> 작성일: 2026-03-18

---

## 1. HIGH — E2E(Phase 6) 전 필수

### 1.1 프롬프트 원본 복원 [HIGH]

**현황**: 4개 Gemini 프롬프트 파일이 72-85% 축약됨.

| 파일 | 원본 줄 | 현재 줄 | 삭제율 |
|------|---------|---------|--------|
| `gemini_vision_prompt.py` | 242 | 37 | 85% |
| `gemini_ai_prompt.py` | 253 | 38 | 85% |
| `gemini_mode_prompt.py` | 155 | 43 | 72% |
| `gemini_post_motion_prompt.py` | 79 | 33 | 58% |

**삭제된 핵심 지시**:
- VISION: IDENTITY MOTION 우선순위, MOVING PART ISOLATION, frame_count/moving_zone/pingpong 판단 기준
- AI_VALIDATOR: GHOSTING 2유형(outline/body drift), 실패 패턴 4종, no_motion 완화, return-to-origin 관대 처리
- MODE: PRE-CHECK 4단계, 물리 속성 기반 판단, suggested_action 10종 가이드

**리스크**: Gemini 응답 품질 저하 → WAN 생성 실패율 상승 + 저품질 영상 통과.

**조치 방법**: `_prompt.py` 파일 내용을 원본 프롬프트 전문으로 교체. 어댑터 코드 변경 불필요.

**200L 초과 대응**:
- `gemini_mode_prompt.py` (155줄): 그대로 복원 가능
- `gemini_post_motion_prompt.py` (79줄): 그대로 복원 가능
- `gemini_vision_prompt.py` (242줄): `PROMPT_PART1 + PROMPT_PART2` 분할 또는 프롬프트 파일 200L 제약 예외
- `gemini_ai_prompt.py` (253줄): 동일

---

## 2. LOW — Phase 6 진행 중 처리

### 2.1 ComfyUI 어댑터 미이식

**현황**: Phase 3 → Phase 5 → Phase 6으로 3차 이연. 현재 DummyAnimationGenerator로 전체 흐름 동작.

**필요 시점**: 실제 ComfyUI 서버 연동 E2E 실행 시.

**이식 범위** (wan_backend.py에서):
- `ComfyUIClient` (줄 745-1070, 326줄) — HTTP 통신
- `WORKFLOW_INJECT_MAP` + CLIP 노드 ID (줄 1072-1110)
- `_gui_workflow_to_api()` (줄 1112-1178)
- `load_workflow_from_file()` (줄 1180-1248)
- `build_wan_workflow()` (줄 1412-1587)
- `_inject_mask_into_workflow()` (줄 1330-1410)
- 글로벌 상수 10개 → Hydra config 전환

총 ~843줄 → 200L 제약 준수 위해 최소 5파일 분할 예상.

### 2.2 전처리 단위 테스트

**현황**: `preprocessing.py`의 `white_anchor()` + `preprocess_image_simple()`에 대한 단위 테스트 미작성. 외부 의존성(PIL + scipy) 필요.

**조치**: Phase 6에서 합성 이미지를 생성하여 테스트 추가.

### 2.3 DummyFormatConverter 빈 경로

**현황**: `DummyFormatConverter.convert()`가 `ConvertedAsset(lottie_path=None, apng_path=None, webm_path=None)` 반환.

**영향**: orchestrator에서 `converted.lottie_path` 등을 참조할 때 None 체크 필요. 현재 orchestrator는 `_post_process()` 반환값을 그대로 `AnimateResult`에 전달하므로 문제 없음.

### 2.4 flows/subflows.py animate_stub 교체

**현황**: `animate_stub()`이 여전히 "not implemented" 반환. Phase 6에서 실제 `AnimateOrchestrator`를 호출하는 구현으로 교체 필요.

---

## 3. 해결 완료 항목 (참고)

| 항목 | 해결 Phase | 해결 방법 |
|------|-----------|----------|
| JSON 복구 로직 4개 어댑터 | Phase 3 리뷰 | 코드 대조로 완전 이식 확인 |
| mode_classifier 3단계 복구 강화 | Phase 5 체크리스트 | `_robust_parse()` 추가 |
| has_deformable 추론 로직 | Phase 5 체크리스트 | processing_mode에서 추론 |
| soft_pass Pydantic immutable | Phase 5 체크리스트 | 새 인스턴스 생성 패턴 확인 |
| bg_type 중국어 프롬프트 | Phase 5 체크리스트 | 원본 전문 복원 |
| 검증 지표 수 표기 (8→9) | Phase 2 체크리스트 | 문서 7곳 정정 |
| VisionAnalysisPort analyze_with_exclusion | Phase 1-2 | 포트 + Dummy에 반영 |
| KeyframeConfig DTO | Phase 3 | domain에 추가 |
| AIValidationContext DTO | Phase 1 | domain에 추가 |
| PostMotion original_image 파라미터 | Phase 1 | 포트 시그니처에 추가 |

---

## 4. 전체 수치 요약

| 항목 | 수치 |
|------|------|
| 총 신규 파일 | 46개 |
| 총 신규 코드 | +5,100줄 이상 |
| 테스트 | 232 passed, 8 skipped, 0 failed |
| HIGH 미해결 | **1건** (프롬프트 복원) |
| LOW 미해결 | **4건** (ComfyUI, 전처리 테스트, Dummy 경로, stub 교체) |
| MEDIUM 미해결 | **0건** (전부 해결) |
