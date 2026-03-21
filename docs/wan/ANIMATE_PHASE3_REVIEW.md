# Animate Integration — Phase 3 주의 사항 및 확인 사항

> Phase 3 (외부 서비스 어댑터 이식) 완료 후 종합 검토
> 검토 기준: 원본 12개 파일 코드 × Phase 3 보고서 × 계획서 × Phase 1-2 체크리스트

---

## 1. 프롬프트 축약 — 동작 동등성 리스크 [HIGH]

### 현황

원본 시스템 프롬프트가 72-85% 축약됨:

| 프롬프트 | 원본 줄 | 축약 줄 | 삭제율 |
|---|---|---|---|
| MODE_CLASSIFIER_PROMPT | 155 | 43 | 72% |
| VISION_SYSTEM_PROMPT | 242 | 37 | 85% |
| AI_VALIDATOR_SYSTEM_PROMPT | 253 | 38 | 85% |
| POST_MOTION_PROMPT | 79 | 33 | 58% |

### 삭제된 핵심 지시 (원본 확인 기반)

**VISION_SYSTEM_PROMPT에서 삭제된 것**:
- PHASE A "IDENTITY MOTION" 개념 전체 — 주체 유형별 가장 자연스러운 모션을 먼저 시도하라는 우선순위 규칙 (원본 줄 71-89)
- PHASE B "EXECUTABLE FORM" — WAN의 픽셀 기반 한계를 고려한 모션 실행 형태 결정 (원본 줄 94-100)
- MOVING PART ISOLATION 원칙 — "최소 부위만 움직이고 나머지는 완전 고정" 지시 (원본 줄 13-14, 별도 섹션으로 상세 설명)
- frame_count 결정 가이드 — 모션 유형별 적정 프레임 수 (9-81 범위 내 판단 기준)
- moving_zone bbox 정밀 지시 — 최소 크기 0.15, 과도한 영역 지정 금지
- pingpong 판단 기준 — "왕복 자연스러운 모션 vs 단방향 모션" 구분 규칙

**AI_VALIDATOR_SYSTEM_PROMPT에서 삭제된 것**:
- GHOSTING 판별 2가지 유형 (OUTLINE GHOST vs BODY DRIFT GHOST) — 원본 줄 134-156, 각각 구체적 판별 질문("Does the body appear in two slightly offset positions?") 포함
- FLICKERING, TEXTURE RECONSTRUCTION, PART INDEPENDENCE 실패 패턴 4종 — 원본 줄 158-179
- no_motion 판정 완화 규칙 — "수치 검증이 통과했으면 AI가 no_motion을 찍지 마라" (원본 줄 103-109)
- return-to-origin 관대 처리 — "전신 점프는 정확한 픽셀 복귀 불필요" (원본 줄 300-302)
- 프롬프트 수정 지시 — 중국어 프롬프트 수정 시 `[该部位]` 패턴 사용 규칙 (원본 줄 270-283)

**MODE_CLASSIFIER_PROMPT에서 삭제된 것**:
- PRE-CHECK 4단계(A: 이산적 주체 존재 여부, B: 복합 주체, C: 비정형/무정형, D: 장면 배경) — 원본 줄 106-145, 각 조건의 상세 설명과 분기
- "물리적 속성 기반 판단" 원칙 — 오브젝트 이름이 아닌 구조(관절, 부착점, 연성 구조)로 판단 (원본 줄 155-174)
- suggested_action 10가지 선택 가이드 (원본 줄 199-246)

### 영향

프롬프트 축약은 Gemini의 응답 품질에 직접 영향:
- **VisionAnalyzer**: 부적절한 action_desc 선택 확률 증가 → WAN 생성 실패율 상승 → 재시도 횟수 증가
- **AIValidator**: ghosting/flickering 미감지 → 저품질 영상이 통과 → 최종 결과물 품질 저하
- **ModeClassifier**: PRE-CHECK 누락 → 비정형 주체나 장면 배경에서 오분류

### 권장 조치

**E2E 테스트(Phase 6) 전에 원본 프롬프트 전문을 `_prompt.py` 파일에 복원**. 프롬프트 파일이 독립 분리되어 있으므로 어댑터 코드 변경 없이 파일 내용만 교체하면 됨.

200줄 제약이 걸리는 경우 프롬프트를 여러 상수로 분할하거나, 프롬프트 파일을 별도 `.txt`로 분리하여 런타임 로드하는 방식도 가능.

---

## 2. JSON 복구 로직 이식 완전성 [MEDIUM]

### 현황

원본 4개 모듈에 각각 다른 JSON 복구 전략이 존재:

| 모듈 | 복구 전략 | 단계 수 |
|---|---|---|
| wan_ai_validator.py | 정상 → reason 필드 제거 재파싱 → passed/issues 정규식 추출 | 3단계 |
| wan_post_motion_classifier.py | 정상 → 따옴표/중괄호 닫기 → `_extract_from_text()` 키워드 추출 | 3단계 |
| wan_mode_classifier.py | 정상 파싱 + `is_scene`/`has_deformable` 교차 검증으로 mode 보정 | 1단계 + 보정 |
| wan_vision_analyzer.py | 정상 파싱 + 수치 클램핑 (frame_rate 8-24, min_motion 0.02-0.25 등) + moving_zone 최소 크기 보장 | 1단계 + 클램핑 |

### 확인 필요

Phase 3 보고서에서 `gemini_common.py`의 `parse_gemini_json(raw)` 공통 함수를 도입했지만, 이 공통 함수가 처리하는 범위와 각 어댑터의 고유 복구 로직이 유지되는지:

1. **gemini_ai_validator.py**: reason 필드 제거 재파싱(2차) + passed/issues 정규식 추출(3차)이 `_parse_response`에 존재하는지
2. **gemini_post_motion.py**: 따옴표/중괄호 수리 + `_extract_from_text()` 키워드 fallback이 존재하는지
3. **gemini_mode_classifier.py**: `processing_mode` vs `is_scene`/`has_deformable` 교차 검증 + 불일치 시 경고 로그가 존재하는지
4. **gemini_vision_analyzer.py**: 수치 클램핑 (frame_rate max(8,min(24,...)), min_motion, max_motion 관계 보정, moving_zone 최소 0.15 보장, positive/negative 최소 길이 10자 검증)이 존재하는지

**이 4가지 고유 복구 로직 중 하나라도 누락되면 운영 시 Gemini 응답 파싱 실패가 발생하여 재시도 낭비 또는 잘못된 파라미터로 WAN 생성이 진행됨.**

### 권장 조치

각 어댑터의 `_parse_response` 메서드를 원본과 diff하여 복구 로직 완전성 확인.

---

## 3. wan_ai_validator 비디오 전달 방식 — 보고서 기술 정정 [LOW]

### 현황

Phase 3 보고서 섹션 2.2 테이블에서 GeminiAIValidator의 Gemini 입력을 "원본 이미지 + 비디오 (inline/upload)"로 기술.

### 원본 확인 결과

원본 wan_ai_validator.py(줄 409-484) 확인:
- 원본 이미지: `PILImage.open(original_path)` — PIL 이미지 직접 전달
- 비디오: `video_bytes` → 18MB 미만 inline blob / 18MB 이상 File API upload — **mp4 바이트 직접 전달**
- 컨텍스트 프롬프트: `current_fps`, `current_scale`, `positive`, `negative`를 텍스트로 전달

보고서에서 이전에 "5프레임 추출"로 기술했던 부분은 **원본 시스템 프롬프트의 설명**(줄 72-75: "Five frames from the generated animation: FIRST(0%), QUARTER(25%), MIDDLE(50%), THREE-QUARTER(75%), LAST(100%)")이지, 실제 코드에서 프레임을 추출하는 것이 아님. **Gemini가 비디오를 받아서 내부적으로 프레임을 샘플링하는 것**.

### 영향

Phase 3 보고서의 기술은 정확함. 이전 Phase 1-2 체크리스트(항목 4.1)에서 "wan_ai_validator.py는 영상을 프레임 이미지로 분해해서 전달"이라고 기술한 것이 **오류**였음. 정정 완료. 코드 영향 없음.

---

## 4. ComfyUI 어댑터 Phase 5 이연 — Phase 4 차단 여부 [LOW]

### 현황

계획서 항목 13(ComfyUI)이 Phase 3 → Phase 5로 이연됨. Phase 4는 Dummy 어댑터 + 테스트.

### 확인 결과

Phase 4에서 `DummyAnimationGenerator`가 `AnimationGenerationPort`를 구현하므로 ComfyUI 실제 어댑터 없이 전체 포트 계약 테스트 가능. 계획서의 Dummy 예시(줄 535-541):
```python
def generate(self, handle, uploaded_image, params):
    return AnimationResult(video_path=Path("/tmp/dummy.mp4"), seed=42, attempt=1)
```

**차단 없음 확인.**

---

## 5. format_converter — output_apng/output_webm 플래그 제거 [LOW]

### 현황

원본 `wan_bg_remover.py`의 `remove_background()`에는 `output_apng: bool = True`, `output_webm: bool = True` 선택 플래그가 있었음. Phase 3에서 FormatConversionPort로 분리하면서 이 플래그를 제거하고 "항상 3포맷 전부 생성"으로 변경.

### 영향

원본 wan_backend.py에서의 실제 호출 패턴:
- `generate()` 내부 (줄 1941-1947): `output_apng=True, output_webm=True` — 둘 다 True
- `finalize_manual_selection()` (줄 2457-2461): `output_apng=True` — WebM은 명시 안 함 (기본 True)

모든 호출이 True이므로 플래그 제거의 실질적 영향 없음. 다만 Lottie 변환은 원본에서 별도 단계(`wan_lottie_converter.py`)로 호출되었고 bg_remover와 동시에 실행되지 않았음.

### 주의

FormatConversionPort가 APNG + WebM + Lottie 3포맷을 한 번에 생성하는데, **Lottie 변환은 해상도 프리셋(original/web/web_hd/mobile)에 따라 다른 결과를 생성**하므로 `convert()` 메서드에 preset 파라미터가 올바르게 전달되는지 Phase 5 orchestrator에서 확인 필요.

---

## 6. get_lottie_info() 미이식 — Phase 5 영향 [LOW]

### 현황

원본 `wan_lottie_converter.py`의 `get_lottie_info()` 유틸이 미이식됨.

### 원본 사용처

wan_server.py(줄 — REST API)에서 프론트엔드 대시보드에 Lottie 정보를 전달할 때 사용. wan_backend.py의 orchestrator 로직에서는 직접 사용하지 않음.

단, wan_dashboard.html의 **Lottie + CSS 키프레임 동기화**(WAN_I2V_SESSION5_CONTEXT.md 섹션 8)에서 `duration_ms`를 참조하여 키프레임 duration을 동기화하는데, 이 `duration_ms`는 `get_lottie_info()`가 반환하는 값.

### 영향

- engine의 CLI/Prefect 경로: 영향 없음 (대시보드 미사용)
- 향후 대시보드 연동 시: `get_lottie_info()` 또는 동등 유틸 필요

### 권장 조치

Phase 5 orchestrator가 Lottie `duration_ms`를 필요로 하면 `format_converter.py`에 `get_info(lottie_path) → dict` 메서드를 추가. 현재는 미이식 상태 유지.

---

## 7. preprocessing — scipy 의존성 [LOW]

### 현황

`preprocessing.py`의 `white_anchor()` 함수가 `scipy.ndimage.label()`을 사용 (테두리 연결 배경 픽셀 flood fill).

### 계획서 대조

ANIMATE_INTEGRATION_PLAN.md 섹션 2.5: "`preprocessing.py` — white_anchor, padding, 리사이즈. 도메인 로직 (외부 의존성 없음)"

**실제로는 scipy 의존성이 있음.** 계획서의 "외부 의존성 없음" 기술이 부정확.

### 영향

`pyproject.toml`의 `animate` optional extra에 이미 `scipy>=1.11.0`이 포함되어 있으므로 런타임 문제는 없음. 다만 `preprocessing.py`를 `application/use_cases/animate/` (Use Case 레이어)에 배치한 것은 헥사고날 원칙상 논의 가능 — Use Case 레이어에 외부 라이브러리(scipy) 직접 의존이 있는 것.

### 권장 조치

두 가지 옵션:
- **A) 현재 위치 유지**: white_anchor는 도메인 전처리 로직이며 scipy.ndimage는 사실상 numpy 확장. 실용적으로 허용.
- **B) adapters/outbound/animate/preprocessing.py로 이동**: 엄격한 헥사고날 원칙 준수. 다만 과도한 분리일 수 있음.

A안 권장 — 현 상태 유지.

---

## 8. Gemini temperature 차이 — 어댑터별 설정 [LOW]

### 현황

원본 4개 모듈의 Gemini 호출 temperature가 각각 다름:

| 모듈 | temperature | 이유 |
|---|---|---|
| wan_mode_classifier.py | 0.1 | 결정론적 분류 (KEYFRAME_ONLY vs MOTION_NEEDED) |
| wan_vision_analyzer.py | 0.3 (일반) / 0.5 (exclusion) | 자유도 있는 파라미터 결정 / 액션 전환 시 다양성 |
| wan_ai_validator.py | 0.2 | 준결정론적 품질 판정 |
| wan_post_motion_classifier.py | 0.1 | 결정론적 분류 (3카테고리) |

### 확인 필요

Phase 3 보고서에서 `__init__`에 temperature를 저장한다고 했지만, `analyze_with_exclusion()`이 일반 `analyze()`와 다른 temperature(0.5)를 사용하는 패턴이 유지되는지 확인 필요.

---

## 9. 요약 — 심각도별 정리

| # | 항목 | 심각도 | 조치 |
|---|------|--------|------|
| 1 | 프롬프트 축약 — 원본 복원 필요 | **HIGH** | E2E 전에 `_prompt.py` 4개에 원본 프롬프트 전문 복원 |
| 2 | JSON 복구 로직 이식 완전성 | **MEDIUM** | 4개 어댑터의 `_parse_response`를 원본과 diff |
| 3 | wan_ai_validator 비디오 전달 — 이전 기술 정정 | LOW | 프레임 추출이 아닌 mp4 직접 전달 — 코드 영향 없음 |
| 4 | ComfyUI Phase 5 이연 → Phase 4 차단 없음 | LOW | Dummy로 대체 확인 완료 |
| 5 | format_converter 플래그 제거 | LOW | 실사용 패턴에서 항상 True — 영향 없음 |
| 6 | get_lottie_info() 미이식 | LOW | Phase 5에서 필요 시 추가 |
| 7 | preprocessing scipy 의존성 | LOW | pyproject.toml에 이미 포함, 현 위치 유지 |
| 8 | Gemini temperature 차이 | LOW | analyze_with_exclusion의 0.5 유지 확인 |

**차단 이슈: 0건.**
**HIGH 1건**: 프롬프트 원본 복원 — Phase 4 진행에는 영향 없으나 E2E(Phase 6) 전에 반드시 처리.
**MEDIUM 1건**: JSON 복구 로직 — Phase 4/5 진행 가능하나 E2E 전에 확인 필요.
