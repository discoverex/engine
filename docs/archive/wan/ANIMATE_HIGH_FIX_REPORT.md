# Animate HIGH 이슈 수정 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 대상: sprite_gen ↔ engine 비교에서 발견된 HIGH 심각도 2건

---

## 1. 발견 경위

sprite_gen 원본 파일(`wan_mode_classifier.py`)과 engine 이식 파일을 전수 비교하여
기능적으로 누락된 항목을 식별. HIGH 2건, MEDIUM 3건, LOW 3건 중 HIGH 2건을 우선 수정.

---

## 2. HIGH #1 — RIGID BODY RULE 프롬프트 섹션 누락

### 증상

`gemini_mode_prompt.py`의 Q1 섹션에서 원본의 **CRITICAL — RIGID BODY RULE** 전체 블록이 누락.
금속/기계 부품의 강체 분류 지침이 없어 Gemini가 열쇠, 동전, 검 등 강체 오브젝트를
`motion_needed`로 잘못 분류할 가능성 증가.

### 누락 내용 (원본 171-195라인)

- **RIGID 예시** 6줄: 열쇠, 동전, 검, 기어, 병, 상자 등
- **NOT RIGID 예시** 6줄: 가위, 펜치, 체인, 인형, 꽃 등
- **ASK YOURSELF** 자문 가이드: "Can I see a joint, hinge, or flexible connection?"
- OUTPUT FORMAT의 JSON 필드 순서 불일치 + `CRITICAL` 코멘트 누락

### 수정 내용

| 파일 | 변경 |
|------|------|
| `gemini_mode_prompt.py` | Q1 "Answer NO" 뒤에 RIGID BODY RULE 전체 블록 복원 (25줄) |
| `gemini_mode_prompt.py` | OUTPUT FORMAT JSON 필드 순서를 원본과 일치 + `CRITICAL` 코멘트 복원 |

### 수정 후 라인 수

190라인 (200라인 제약 준수)

---

## 3. HIGH #2 — 강체 패턴 감지 로직 단순화

### 증상

`gemini_mode_classifier.py`의 Stage 3 (JSON 파싱 완전 실패 시 fallback) 로직이
원본 대비 극도로 단순화되어 있었음.

| 항목 | 원본 | 엔진 (수정 전) |
|------|------|---------------|
| 강체 부정 표현 패턴 | 18개 (영문) + 8개 (중국어) = **26개** | 0개 |
| NO_DEFORM 표현 패턴 | **11개** | 0개 |
| has_deformable 판정 | 다단계 (키/값 → 교차검증 → 패턴매칭 → fallback) | 단일 문자열 슬라이싱 |
| is_scene 추출 | ✅ | ❌ 항상 False |
| facing_direction 추출 | ✅ 4방향 순회 | ❌ 미추출 |
| suggested_action 추출 | ✅ 10종 순회 | ❌ 미추출 |

### 영향

JSON이 깨진 Gemini 응답에서:
- 강체 오브젝트가 `motion_needed`로 잘못 분류 (불필요한 GPU 자원 소모)
- `is_scene`, `facing_direction`, `suggested_action` 정보 손실
- 중국어 응답 처리 불가

### 수정 내용

| 파일 | 변경 |
|------|------|
| `gemini_mode_fallback.py` **(신규)** | 원본 `_extract_from_text()` 전체 이식 |
| `gemini_mode_classifier.py` | Stage 3에서 `gemini_mode_fallback.extract_from_text()` 호출로 교체 |

### 복원된 패턴 목록

**강체 부정 표현 (_NEGATIVE_PATTERNS, 26개)**:
```
영문: no joint, no hinge, no articulation, no pivot, no flexible,
      no deformable, no moving part, does not bend/flex/deform,
      cannot bend/flex, rigid body/object, single solid,
      one solid piece, fused together, moves as one unit,
      all parts are rigidly, no visible joint

중국어: 没有关节, 没有铰链, 不弯曲, 不变形, 刚性, 刚体, 一体, 整体移动
```

**NO_DEFORM 표현 (_NO_DEFORM_EXPRESSIONS, 11개)**:
```
answer no, answer is no, would not change shape, would not deform,
outline shape would not, shape does not change,
maintains its exact shape, maintains its shape,
no part would bend, no part would flex, whole subject moves as one
```

### 수정 후 라인 수

| 파일 | 라인 |
|------|------|
| `gemini_mode_classifier.py` | 148 |
| `gemini_mode_fallback.py` (신규) | 110 |
| `gemini_mode_prompt.py` | 190 |

전체 200라인 제약 준수.

---

## 4. 검증 결과

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success: no issues found in 3 source files |
| 200라인 제약 | 0건 위반 (148 / 110 / 190) |
| animate 테스트 (33건) | 33 passed |
| 전체 테스트 (234건) | **234 passed, 8 skipped, 0 failed** |

---

## 5. 파일 변경 요약

| 파일 | 유형 | 변경 내용 |
|------|------|----------|
| `adapters/outbound/models/gemini_mode_prompt.py` | 수정 | RIGID BODY RULE 블록 복원 + OUTPUT FORMAT 원본 정렬 |
| `adapters/outbound/models/gemini_mode_fallback.py` | **신규** | Stage 3 키워드 추출 + 강체 패턴 감지 (원본 전체 이식) |
| `adapters/outbound/models/gemini_mode_classifier.py` | 수정 | Stage 3에서 fallback 모듈 호출로 교체 |

---

## 6. 잔여 이슈 (MEDIUM/LOW)

| # | 항목 | 심각도 | 상태 |
|---|------|--------|------|
| 1 | wan_vision_analyzer 프롬프트 축약 | MEDIUM | 미처리 |
| 2 | wan_ai_validator 프롬프트 축약 | MEDIUM | 미처리 |
| 3 | wan_backend 이력 기반 negative 강화 미구현 | MEDIUM | 미처리 |
| 4 | wan_post_motion_classifier 확장자 검증 제거 | LOW | 미처리 |
| 5 | wan_post_motion_classifier fallback suggested_keyframe 추출 제거 | LOW | 미처리 |
| 6 | wan_backend _ValidationStats 통계 추적 제거 | LOW | 미처리 |
