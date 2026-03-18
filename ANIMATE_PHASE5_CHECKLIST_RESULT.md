# Animate Integration — Phase 5 체크리스트 반영 결과

> ANIMATE_PHASE5_CHECKLIST.md 항목별 조치 내역
> 반영일: 2026-03-18

---

## 1. 반영 완료 항목

### 1.1 soft_pass Pydantic immutable 문제 → RESOLVED

**체크리스트 우려**: `AIValidationFix`가 Pydantic BaseModel이므로 직접 속성 수정(`ai_result.passed = True`)이 문제될 수 있음.

**실제 코드 확인** (`retry_loop.py:115`):
```python
ai = AIValidationFix(passed=True, issues=ai.issues, reason="soft_pass")
```
직접 수정이 아닌 **새 인스턴스 생성** 패턴 사용. frozen 여부와 무관하게 안전.

**조치**: 없음 (이미 안전).

---

### 1.2 bg_type별 중국어 프롬프트 정확성 → 반영 완료

**체크리스트 우려**: retry_state.py의 배경 프롬프트가 원본보다 축약되어 있음.

**반영 내용** (`retry_state.py:44-58`):
- solid 배경: 원본(wan_backend.py 줄 1764-1772)과 동일한 8항목 positive + 13항목 negative 복원
- scene 배경: 원본(줄 1775-1781)과 동일한 3항목 positive + 5항목 negative 복원

**커밋**: `46b77da`

---

### 2.1A mode_classifier JSON 3단계 복구 → 반영 완료

**체크리스트 지시**: wan_mode_classifier.py에서 운영 중 발견된 연속 파싱 실패를 방지하는 3단계 복구 로직 추가.

**반영 내용** (`gemini_mode_classifier.py:24-57`, `_robust_parse()` 함수):

| 단계 | 처리 | 성공 조건 |
|------|------|----------|
| 1차 | `parse_gemini_json()` 정상 파싱 | 핵심 필드(has_deformable_parts/processing_mode) 존재 |
| 2차 | 따옴표/중괄호 수리 후 재파싱 | 동일 |
| 3차 | 키워드 기반 추출 (`"keyframe_only"` 검색 등) | 항상 성공 (fallback) |

**커밋**: `46b77da`

---

### 2.1B has_deformable_parts 누락 시 추론 → 반영 완료

**체크리스트 지시**: `has_deformable_parts` 필드가 Gemini 응답에 누락되면 `processing_mode`에서 추론.

**반영 내용** (`gemini_mode_classifier.py:79-84`):
```python
if "has_deformable_parts" in data:
    has_deformable = bool(data["has_deformable_parts"])
elif data.get("processing_mode") == "keyframe_only":
    has_deformable = False  # keyframe_only면 변형 불필요
else:
    has_deformable = True   # 불명확 → 안전 방향(MOTION_NEEDED)
```

**커밋**: `46b77da`

---

### 2.2 나머지 3개 어댑터 JSON 복구 로직 → RESOLVED (이전 확인)

**체크리스트 지시**: gemini_ai_validator, gemini_post_motion, gemini_vision_analyzer의 고유 복구 로직 확인.

**확인 결과** (Phase 3 리뷰에서 코드 대조 완료):

| 어댑터 | 확인 항목 | 상태 |
|--------|----------|------|
| gemini_ai_validator.py | 3단계 (정상→reason 제거→regex 추출) | ✅ 완전 이식 |
| gemini_post_motion.py | 따옴표 수리 + _extract_from_text | ✅ 완전 이식 |
| gemini_vision_analyzer.py | frame_rate(8-24), min_motion(0.02-0.25), moving_zone(0.15), 길이(10자) | ✅ 완전 이식 |

**조치**: 없음 (이미 확인 완료).

---

## 2. 검증 결과

| 검증 | 결과 |
|------|------|
| `ruff check` | All checks passed |
| `mypy` | Success: no issues found |
| `pytest` (전체) | **232 passed, 8 skipped, 0 failed** |
| 200L 제약 | gemini_mode_classifier.py 152L, retry_state.py 71L — 모두 이내 |
