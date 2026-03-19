# Animate MEDIUM 이슈 수정 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 대상: sprite_gen ↔ engine 비교에서 발견된 MEDIUM 심각도 2건 (프롬프트 축약)

---

## 1. 발견 경위

sprite_gen 원본과 engine 이식 파일 전수 비교 시, Gemini Vision Analyzer와
AI Validator의 시스템 프롬프트가 200라인 제약 대응 과정에서 대폭 축약된 것을 확인.

원본 프롬프트의 상세 예시, 판단 원칙, 수정 가이드가 제거되어
AI 의사결정 정밀도가 저하될 수 있는 상태였음.

---

## 2. MEDIUM #1 — Vision Analyzer 프롬프트 축약 (133줄 → 원본 242줄)

### 누락 항목

| 섹션 | 누락 내용 |
|------|----------|
| PHASE A | "Not what motion is safe — what motion makes this subject feel alive" 동기 부여 문구 |
| PHASE A | "Head nods, tail twitches = LAST RESORT fallbacks, used only after identity motion failed 3 times" |
| PHASE B | Q1/Q2/Q3 필터별 상세 예시 (Bird wing fold/unfold, Fish S-curve 등) |
| PHASE B | "If the full form fails Q2, use a PARTIAL form — keep the intent" 가이드 |
| STEP 3.5 | 바운딩박스 좌표 예시 3건 (Tail, Head, Fin) |
| STEP 5 | FORBIDDEN words 상세 설명 ("Do NOT use: any phrase that implies the whole body rotates") |
| STEP 5 | SPECIAL CASE (full body jump) 프롬프트 작성 가이드 3줄 |
| STEP 7 | 각 구간별 추론 로직 ("fewer frames = less time for WAN to introduce deformation artifacts") |
| STEP 7 | MEDIUM/LONG 구간 상세 예시 (tail sweep, frog jump crouch→launch→airborne→land) |
| STEP 8 | pingpong CORE PRINCIPLE 전체 블록 (~30줄) |
| STEP 8 | "Judge by the POSE, not the background" 원칙 |
| STEP 8 | pingpong=false/true 판단 기준 상세 설명 |

### 수정 내용

원본 `wan_vision_analyzer.py` 58-299줄의 프롬프트 전문을 복원.
200라인 제약 준수를 위해 3파일로 물리 분할:

| 파일 | 라인 | 내용 |
|------|------|------|
| `gemini_vision_prompt.py` | 9 | assembler (import + 결합) |
| `gemini_vision_prompt_parts.py` **(신규)** | 118 | STEP 1-4, PHASE A/B, ALWAYS AVOID, SPECIAL CASE |
| `gemini_vision_prompt_steps.py` **(신규)** | 138 | STEP 5-8, OUTPUT FORMAT |

---

## 3. MEDIUM #2 — AI Validator 프롬프트 축약 (124줄 → 원본 253줄)

### 누락 항목

| 섹션 | 누락 내용 |
|------|----------|
| 도입부 | 5프레임 구조 설명 (FIRST/QUARTER/MIDDLE/THREE-QUARTER/LAST 각 역할) |
| 도입부 | "do NOT judge motion by comparing FIRST vs MIDDLE" 판단 원칙 |
| [1] SPEED | 도메인별 속도 예시 (frog jump snappy, bird wing rapid, fish swim gentle) |
| [1] no_motion | "breathing-like tremor", "Sprite animations with gentle ambient motion" 상세 |
| [4] GHOSTING | TWO FORMS 상세 설명 (Outline Ghost 5줄, Body Drift Ghost 5줄) |
| [4] GHOSTING | KEY DISTINCTION from acceptable motion blur 상세 비교 |
| [4] FLICKERING | "instead of tracing a smooth continuous arc, it snaps" 상세 설명 |
| [4] PART INDEPENDENCE | FAIL/PASS 구체적 구분 4건 (wing blurry, limb bends vs micro-vibration) |
| [4] PASS examples | "2D CARTOON SPECIFIC: Subtle pixel jiggling" 수용 기준 |
| [4] motion blur vs ghosting | 상세 구분 가이드 ("frozen BODY appears soft → always GHOSTING FAIL") |
| [5] CHARACTER | body part DISAPPEARS 검출 가이드 3줄 (wing dissolving, body fading) |
| [6] BACKGROUND | Category A/B 상세 예시 ("white background turned grey, bird looks perfect → PASS") |
| IF ISSUES | STEP A-G 상세 가이드 전체 (23줄 → 원본 58줄) |
| IF ISSUES | STEP B 필터 상세 (❌ pulsates, ❌ pixel change too small, ❌ structurally deform) |
| IF ISSUES | STEP C 대체 파트 선정 기준 3건 (✅ visible, ✅ sweep/tilt/rotate, ✅ small relative) |
| IF ISSUES | naturalness: NEGATIVE IS PRIMARY 원칙 + Chinese 프롬프트 예시 4건 |
| IF ISSUES | return-to-origin: full body jump 예외 규칙 ("exact pixel return NOT required") |

### 수정 내용

원본 `wan_ai_validator.py` 70-322줄의 프롬프트 전문을 복원.
200라인 제약 준수를 위해 3파일로 물리 분할:

| 파일 | 라인 | 내용 |
|------|------|------|
| `gemini_ai_prompt.py` | 9 | assembler (import + 결합) |
| `gemini_ai_prompt_criteria.py` **(신규)** | 176 | Review Criteria [1]-[6] 전문 |
| `gemini_ai_prompt_fixes.py` **(신규)** | 90 | STEP A-G 수정 가이드 + OUTPUT FORMAT |

---

## 4. 검증 결과

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed (6 files) |
| mypy strict | Success: no issues found in 6 source files |
| 200라인 제약 | 0건 위반 (9 / 118 / 138 / 9 / 176 / 90) |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |

---

## 5. 파일 변경 요약

### Vision Analyzer 프롬프트

| 파일 | 유형 | 변경 |
|------|------|------|
| `gemini_vision_prompt.py` | 수정 | assembler로 전환 (PART import + 결합) |
| `gemini_vision_prompt_parts.py` | **신규** | STEP 1-4, PHASE A/B 원본 전문 (118줄) |
| `gemini_vision_prompt_steps.py` | **신규** | STEP 5-8, OUTPUT FORMAT 원본 전문 (138줄) |

### AI Validator 프롬프트

| 파일 | 유형 | 변경 |
|------|------|------|
| `gemini_ai_prompt.py` | 수정 | assembler로 전환 (PART import + 결합) |
| `gemini_ai_prompt_criteria.py` | **신규** | Review Criteria [1]-[6] 원본 전문 (176줄) |
| `gemini_ai_prompt_fixes.py` | **신규** | STEP A-G 수정 가이드 + OUTPUT FORMAT (90줄) |

---

## 6. 설계 판단 — 프롬프트 파일 분할 전략

200라인 제약은 로직 파일의 가독성을 위한 것이나, 프롬프트 상수 파일도 동일 규칙 적용.
분할 전략:

```
gemini_*_prompt.py          ← assembler (import + 결합, ~10줄)
gemini_*_prompt_parts.py    ← 텍스트 상수 파트 A (≤200줄)
gemini_*_prompt_steps.py    ← 텍스트 상수 파트 B (≤200줄)
gemini_*_prompt_fixes.py    ← 텍스트 상수 파트 C (≤200줄, AI만)
```

기존 `_PART1 + _PART2` 패턴을 유지하되, 물리 파일을 분리하여 제약 준수.
assembler 파일이 공개 심볼(`VISION_SYSTEM_PROMPT`, `AI_VALIDATOR_SYSTEM_PROMPT`)을 export하므로
기존 import 경로는 변경 없음.

---

## 7. 잔여 이슈

| # | 항목 | 심각도 | 상태 |
|---|------|--------|------|
| 1 | wan_backend 이력 기반 negative 강화 미구현 | MEDIUM | 미처리 |
| 2 | wan_post_motion_classifier 확장자 검증 제거 | LOW | 미처리 |
| 3 | wan_post_motion_classifier fallback suggested_keyframe 추출 제거 | LOW | 미처리 |
| 4 | wan_backend _ValidationStats 통계 추적 제거 | LOW | 미처리 |

**HIGH 0건 (해소), MEDIUM 1건 (이력 기반 강화), LOW 3건**
