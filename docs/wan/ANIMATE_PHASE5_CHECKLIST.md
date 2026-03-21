# Animate Integration — Phase 5 확인 사항 및 누적 미해결 항목

> Phase 5 (오케스트레이션 & 부트스트랩) 완료 후 종합
> Phase 6 (Flow 연결 & E2E) 착수 전 전수 정리

---

## 1. Phase 5 신규 확인 사항

### 1.1 soft_pass — Pydantic BaseModel immutable 문제 [MEDIUM]

**원본 패턴** (wan_backend.py 줄 1911):
```python
ai_result.passed = True  # mutable dataclass 직접 수정
```

**engine 이식**: Phase 1에서 `AIValidationFix`를 Pydantic `BaseModel`로 정의. Pydantic v2 BaseModel은 기본적으로 attribute 직접 할당이 가능하지만(`model_config`에서 `frozen=True`를 설정하지 않는 한), 코드 의도 명확성을 위해 다음 중 하나로 처리 권장:

```python
# 옵션 A: 직접 할당 (Pydantic v2 기본 동작, frozen 아니면 가능)
ai_result.passed = True

# 옵션 B: 새 인스턴스 (immutable 패턴, 더 안전)
ai_result = ai_result.model_copy(update={"passed": True})
```

**확인 필요**: retry_loop.py의 `_on_pass()` 에서 어떤 방식을 사용했는지 확인. domain/animate.py에서 `AIValidationFix`에 `model_config = ConfigDict(frozen=True)` 설정이 있으면 옵션 A가 런타임 에러 발생.

### 1.2 bg_type별 배경 프롬프트 정확성 [LOW]

**원본** (wan_backend.py 줄 1763-1782):

```python
# solid 배경
BG_POSITIVE = "纯白色背景，整个动画过程中背景始终保持白色，背景干净无杂质，始终保持恒定的亮度，没有闪烁，画面明亮清晰，边缘锐利，无残影"
BG_NEGATIVE = "背景变色，背景变暗，背景变黑，背景变灰，背景变黄，背景变紫，背景颜色偏移，非白色背景，黑屏，阴影遮盖，滤镜感，曝光不足，画面闪烁"

# scene 배경
BG_POSITIVE = "背景保持不变，整个动画过程中背景始终保持原始状态，画面明亮清晰，边缘锐利，无残影"
BG_NEGATIVE = "背景消失，背景模糊，背景扭曲，黑屏，画面闪烁"
```

**확인 필요**: retry_state.py의 `LoopState.rebuild_base_prompts()`에 이 중국어 프롬프트가 정확히 이식되었는지. 문자열 하나라도 다르면 WAN 생성 품질에 영향.

### 1.3 ComfyUI 어댑터 3차 이연 [LOW]

Phase 3 → Phase 5 → Phase 6. Dummy로 전체 흐름 검증 완료. E2E 실행 시 구현 필요.

ComfyUI 어댑터 이식 시 포함되어야 할 원본 코드 범위:
- `ComfyUIClient` (줄 745-1070, 326줄) — HTTP 통신
- `WORKFLOW_INJECT_MAP` + CLIP 노드 ID (줄 1072-1110)
- `_gui_workflow_to_api()` (줄 1112-1178)
- `load_workflow_from_file()` (줄 1180-1248)
- `build_wan_workflow()` (줄 1412-1587)
- `_inject_mask_into_workflow()` (줄 1330-1410)
- 글로벌 상수 10개 → Hydra config 전환

총 ~843줄 → 200L 제약 준수 위해 최소 5파일 분할 예상.

---

## 2. 직전 세션에서 수정한 내용 — engine 반영 필요

### 2.1 wan_mode_classifier.py JSON 복구 로직 강화

**수정 내용 (2건)**:

**A) 3단계 JSON 복구 + 핵심 필드 검증**

```
1차: 정상 json.loads()
2차: 따옴표/중괄호 수리 → 성공해도 핵심 필드(has_deformable_parts, processing_mode) 없으면 3차로
3차: _extract_from_text() 키워드 기반 추출
```

원본에는 복구 로직이 없어 Gemini 응답 JSON이 깨지면 3회 재시도 후 전부 MOTION_NEEDED fallback.
실제 운영에서 연속 6회 파싱 실패 발생 확인 → 수정 적용 후 2차 복구로 정상 동작 확인.

**B) has_deformable_parts 누락 시 추론 로직**

```python
# 기존: 무조건 True (MOTION_NEEDED)
has_deformable = bool(data.get("has_deformable_parts", True))

# 수정: processing_mode에서 추론
if "has_deformable_parts" in data:
    has_deformable = bool(data["has_deformable_parts"])
elif data.get("processing_mode") == "keyframe_only":
    has_deformable = False  # keyframe_only면 변형 불필요
else:
    has_deformable = True   # 불명확 → 안전 방향 유지
```

**engine 반영 위치**: `adapters/outbound/models/gemini_mode_classifier.py`의 `_parse_response()` 메서드.

### 2.2 engine 4개 Gemini 어댑터 전수 확인 필요

이 수정은 mode_classifier에만 적용. 나머지 3개 어댑터도 고유 복구 로직이 원본과 동등한지 확인 필요:

| 어댑터 | 확인 항목 | 원본 위치 |
|--------|----------|----------|
| gemini_mode_classifier.py | ✅ 수정 완료 (현재 스크립트). engine 반영 대기 | 줄 322-387 |
| gemini_ai_validator.py | reason 제거 재파싱 + passed/issues 정규식 추출 | 줄 486-516 |
| gemini_post_motion.py | 따옴표 수리 + _extract_from_text 키워드 fallback | 줄 337-355 |
| gemini_vision_analyzer.py | 수치 클램핑 (frame_rate 8-24, min_motion, moving_zone 0.15 등) | 줄 374-431 |

---

## 3. 프롬프트 원본 복원 상세 [HIGH — E2E 전 필수]

### 복원 대상 4개 파일

| engine 파일 | 원본 소스 | 원본 줄 범위 | 현재 축약 줄 |
|---|---|---|---|
| gemini_mode_prompt.py | wan_mode_classifier.py | 줄 91-246 | 43줄 |
| gemini_vision_prompt.py | wan_vision_analyzer.py | 줄 58-299 | 37줄 |
| gemini_ai_prompt.py | wan_ai_validator.py | 줄 70-322 | 38줄 |
| gemini_post_motion_prompt.py | wan_post_motion_classifier.py | 줄 92-170 | 33줄 |

### 복원 시 200L 제약 대응

원본 프롬프트는 79-253줄. 200L 이내 파일도 있지만 초과하는 파일은:

| 파일 | 프롬프트 줄 수 | 200L 초과 여부 | 대응 |
|---|---|---|---|
| gemini_mode_prompt.py | 155 | ❌ | 그대로 복원 |
| gemini_vision_prompt.py | 242 | ✅ | 2개 상수로 분할 또는 별도 .txt 런타임 로드 |
| gemini_ai_prompt.py | 253 | ✅ | 동일 |
| gemini_post_motion_prompt.py | 79 | ❌ | 그대로 복원 |

**권장**: 초과하는 2개는 프롬프트를 `PROMPT_PART1` + `PROMPT_PART2`로 분할하여 어댑터에서 `PROMPT_PART1 + PROMPT_PART2`로 결합. 또는 docstring이 아닌 `"""..."""` 문자열 상수이므로 200L 제약에서 프롬프트 전용 파일을 예외 처리 가능한지 확인.

---

## 4. 전체 누적 미해결 항목 — Phase 6 착수 전 최종 점검표

### E2E 전 필수 (HIGH/MEDIUM)

| # | 항목 | 심각도 | 상태 | 조치 |
|---|------|--------|------|------|
| 1 | 프롬프트 원본 복원 4개 파일 | **HIGH** | ⬜ 미처리 | `_prompt.py` 교체, 200L 초과 시 분할 |
| 2 | gemini_mode_classifier.py JSON 복구 로직 engine 반영 | **MEDIUM** | ⬜ 미처리 | 직전 수정본 반영 (3단계 복구 + 핵심 필드 검증 + 추론 로직) |
| 3 | gemini_ai_validator.py 복구 로직 diff 확인 | **MEDIUM** | ⬜ 미확인 | reason 제거 재파싱 + 정규식 추출 존재 확인 |
| 4 | gemini_post_motion.py 복구 로직 diff 확인 | **MEDIUM** | ⬜ 미확인 | 따옴표 수리 + 키워드 fallback 존재 확인 |
| 5 | gemini_vision_analyzer.py 클램핑 로직 diff 확인 | **MEDIUM** | ⬜ 미확인 | 수치 범위 + moving_zone + 길이 검증 존재 확인 |
| 6 | soft_pass Pydantic immutable 확인 | **MEDIUM** | ⬜ 미확인 | retry_loop.py `_on_pass()` 확인 |

### Phase 6 진행 중 처리 (LOW)

| # | 항목 | 심각도 | 상태 | 조치 |
|---|------|--------|------|------|
| 7 | bg_type별 중국어 프롬프트 정확성 | LOW | ⬜ | retry_state.py diff |
| 8 | ComfyUI 어댑터 구현 | LOW | ⬜ | E2E 실행 시 구현 |
| 9 | 전처리 단위 테스트 추가 | LOW | ⬜ | white_anchor + preprocess 테스트 |
| 10 | DummyFormatConverter 빈 경로 | LOW | ⬜ | orchestrator에서 None 허용 확인 |

---

## 5. 전체 Phase 1-5 수치 요약

| 항목 | 수치 |
|------|------|
| 신규 파일 | 45개 |
| 신규 코드 | +4,883줄 |
| 테스트 | 232 passed, 8 skipped, 0 failed |
| 200L 위반 | 0건 |
| mypy strict 에러 | 0건 |
| 차단 이슈 | 0건 |
| HIGH 미해결 | 1건 (프롬프트 복원) |
| MEDIUM 미해결 | 5건 (JSON 복구 4 + soft_pass 1) |
| LOW 미해결 | 4건 |
