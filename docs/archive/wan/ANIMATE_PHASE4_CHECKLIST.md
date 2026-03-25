# Animate Integration — Phase 4 확인 사항 정리

> Phase 4 (Dummy 어댑터 & 테스트) 완료 후, Phase 5 착수 전 확인 사항 종합
> 이전 Phase 미해결 항목 포함

---

## 1. Phase 4 확인 사항

### 1.1 전처리/수치 검증 단위 테스트 이연 [LOW]

**현황**: 계획서 항목 18에 "전처리, 수치 검증 단위 테스트" 포함이었으나, "외부 의존성(PIL, numpy, ffmpeg) 필요"로 E2E(Phase 6)로 이연.

**정밀 검토**: ffmpeg가 필요한 것은 `numerical_validator`(프레임 추출)와 `bg_remover`뿐. `preprocessing.py`의 `white_anchor()`는 PIL + scipy + numpy만 사용하며, 이들은 `animate` optional extra에 이미 포함되어 CI에서 실행 가능.

**권장**: Phase 6에서 합성 이미지로 `white_anchor()` + `preprocess_image_simple()` 단위 테스트 추가. 차단 이슈 아님.

### 1.2 DummyFormatConverter 빈 ConvertedAsset 반환 [LOW]

**현황**: `ConvertedAsset(lottie_path=None, apng_path=None, webm_path=None)` — 모든 경로 None.

**영향**: Phase 5 orchestrator가 변환 결과 경로를 참조하는 로직이 있으면 None 체크 필요. 원본 wan_backend.py에서 Lottie/APNG/WebM 경로를 orchestrator가 직접 사용하는 패턴은 없음(대시보드에서만 사용).

**권장**: Phase 5 orchestrator 구현 시 `ConvertedAsset` 필드가 None일 수 있음을 전제로 코딩. 또는 DummyFormatConverter가 tempdir에 더미 파일을 생성하여 실제 경로를 반환하도록 개선.

---

## 2. Phase 3에서 이월된 미해결 항목 (Phase 5/6 전 필수)

### 2.1 프롬프트 축약 — 원본 복원 필요 [HIGH]

**원본 출처**: Phase 3 리뷰 항목 1

**현황**: 4개 프롬프트 파일이 72-85% 축약됨.

| 프롬프트 파일 | 원본 줄 | 축약 줄 | 삭제된 핵심 지시 |
|---|---|---|---|
| gemini_vision_prompt.py | 242 | 37 | IDENTITY MOTION, MOVING PART ISOLATION, frame_count/moving_zone/pingpong 판단 기준 |
| gemini_ai_prompt.py | 253 | 38 | GHOSTING 2유형, 실패 패턴 4종, no_motion 완화, return-to-origin 관대 처리 |
| gemini_mode_prompt.py | 155 | 43 | PRE-CHECK 4단계, 물리 속성 기반 판단 원칙, suggested_action 10종 가이드 |
| gemini_post_motion_prompt.py | 79 | 33 | AMPLIFY 3유형 구분 상세 기준 |

**리스크**: Gemini 응답 품질 저하 → WAN 생성 실패율 상승 + 저품질 영상 통과.

**조치 시점**: E2E 테스트(Phase 6) 전에 반드시 원본 전문 복원. `_prompt.py` 파일 교체만으로 충분, 어댑터 코드 변경 불필요.

### 2.2 JSON 복구 로직 이식 완전성 [RESOLVED]

**원본 출처**: Phase 3 리뷰 항목 2

**현황**: Phase 3 리뷰 시 코드 대조 완료. 4개 어댑터 모두 고유 복구 로직 완전 이식 확인:

1. ✅ `gemini_ai_validator.py`: 3단계 복구 (정상 → reason 제거 재파싱 → passed/issues 정규식 추출)
2. ✅ `gemini_post_motion.py`: 따옴표/중괄호 수리 + `_extract_from_text()` 키워드 fallback
3. ✅ `gemini_mode_classifier.py`: is_scene/has_deformable 교차 검증으로 mode 결정
4. ✅ `gemini_vision_analyzer.py`: frame_rate(8-24), min_motion(0.02-0.25), moving_zone(최소 0.15), positive/negative(10자) 클램핑

**추가 조치 불필요.**

---

## 3. Phase 5 착수 시 확인/결정 필요 항목

### 3.1 retry_loop — _ValidationStats 이력 대체 전략 확인 [MEDIUM]

**원본 출처**: 계획서 섹션 3, Phase 3 보고서 줄 420-426

**확정된 방안**: 세션 내 메모리 기반 (`dict[str, Counter]`). 이전 실행 이력 포기, MAX_RETRIES 7-10회 내에서 충분.

**Phase 5 구현 시 확인**: `RetryLoop._build_prompts()`에서 현재 세션의 실패 이력을 Counter로 집계하여 빈도 2회 이상 이슈를 negative에 추가하는 로직이 원본(wan_backend.py 줄 1789-1829)과 동등하게 동작하는지.

### 3.2 ComfyUI 어댑터 — 글로벌 상수 Hydra config 전환 [MEDIUM]

**원본 출처**: Phase 1-2 체크리스트 항목 10

**전환 대상 10개 상수**:

| 상수 | 원본 줄 | Hydra config 키 |
|---|---|---|
| `COMFYUI_URL` | 69 | `comfyui.url` |
| `WAN_MODEL` | 70 | `comfyui.wan_model` |
| `CLIP_MODEL` | 71 | `comfyui.clip_model` |
| `VAE_MODEL` | 72 | `comfyui.vae_model` |
| `COMFYUI_ROOT` | 77-80 | `comfyui.root_dir` |
| `WAN_WORKFLOW_PATH` | 87-94 | `comfyui.workflow_path` |
| `POSITIVE_CLIP_NODE_ID` | 1108 | `comfyui.positive_clip_node_id` |
| `NEGATIVE_CLIP_NODE_ID` | 1109 | `comfyui.negative_clip_node_id` |
| `MAX_RETRIES` | 66 | `pipeline.max_retries` (AnimatePipelineConfig에 존재) |
| `ATTEMPT_OFFSET` | 67 | `pipeline.attempt_offset` |

### 3.3 orchestrator — finalize_manual_selection 이식 여부 [LOW]

**현황**: 원본 `WanBackend.finalize_manual_selection()`(줄 2356-2471, 116줄)은 사용자가 수동으로 영상을 선택하여 최종 처리하는 메서드. 자동 파이프라인 실패 시 사용.

**검토**: engine의 animate flow는 CLI/Prefect 배치 실행이 주 경로. 수동 선택은 대시보드(wan_server.py) 기능이며, 대시보드는 engine 제외 대상.

**판단**: Phase 5에서 미이식. 향후 engine에 interactive 모드가 추가되면 그때 구현.

### 3.4 orchestrator — classify_post_motion 호출 시점 [LOW]

**현황**: 원본에서 Stage 2(`classify_post_motion`)는 `generate()` 내부에서 자동 호출되지 않고, 사용자가 영상 확인 후 수동 호출(줄 2267-2350).

**engine 적용 시**: CLI/Prefect 배치에서는 자동 호출이 자연스러움. orchestrator가 성공 영상에 대해 자동으로 `PostMotionClassificationPort.classify()`를 호출하는 것이 적절.

**Phase 5 구현 시 결정**: orchestrator의 성공 경로에서 post_motion 분류를 자동 실행할지, 별도 단계로 분리할지.

### 3.5 orchestrator — 성공 결과 누적 vs 즉시 반환 [LOW]

**현황**: 원본 wan_backend.py의 `generate()`(줄 1844-1970)는 성공해도 루프를 계속 진행하여 MAX_RETRIES 전부 소진 후 첫 번째 성공 결과를 반환하는 패턴. 이유: "가능한 많은 후보를 생성하여 사용자가 선택"(대시보드 용도).

**engine 적용 시**: 배치 파이프라인에서는 첫 번째 성공 시 즉시 반환이 효율적. MAX_RETRIES 전부 소진은 GPU 시간 낭비.

**Phase 5 구현 시 결정**: `first_success_returns: bool` config 옵션 추가, 또는 engine에서는 항상 즉시 반환으로 고정.

---

## 4. 누적 테스트 현황

| Phase | 신규 파일 | 신규 줄 | 신규 테스트 | 누적 테스트 | pytest 결과 |
|-------|----------|---------|-----------|-----------|------------|
| 1 | 4 | 408 | 0 | 201 | 201 passed |
| 2 | 10 | 787 | 0 | 201 | 201 passed |
| 3 | 11 | 970 | 0 | 201 | 201 passed |
| 4 | 4 | 551 | 30 | 231 | 231 passed |
| **합계** | **29** | **2,716** | **30** | **231** | **0 failed** |

---

## 5. 요약 — 심각도별 정리

| # | 항목 | 심각도 | Phase | 조치 시점 |
|---|------|--------|-------|----------|
| 1 | 프롬프트 원본 복원 | **HIGH** | 3 이월 | E2E(Phase 6) 전 |
| 2 | JSON 복구 로직 완전성 확인 | ~~MEDIUM~~ **RESOLVED** | 3 이월 | Phase 3 리뷰에서 확인 완료 |
| 3 | retry_loop 이력 대체 구현 확인 | **MEDIUM** | 5 | Phase 5 구현 시 |
| 4 | ComfyUI 글로벌 상수 Hydra 전환 | **MEDIUM** | 5 | Phase 5 구현 시 |
| 5 | 전처리 단위 테스트 이연 | LOW | 4 | Phase 6 |
| 6 | DummyFormatConverter 빈 경로 | LOW | 4 | Phase 5 orchestrator 구현 시 |
| 7 | finalize_manual_selection 미이식 | LOW | 5 | 미이식 (대시보드 기능) |
| 8 | classify_post_motion 자동 호출 여부 | LOW | 5 | Phase 5 구현 시 결정 |
| 9 | 성공 시 즉시 반환 vs 누적 | LOW | 5 | Phase 5 구현 시 결정 |

**차단 이슈: 0건. Phase 5 착수 가능.**
