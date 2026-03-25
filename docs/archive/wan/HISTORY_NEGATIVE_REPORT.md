# 이력 기반 Negative 강화 기능 구현 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 커밋: c4bd265

---

## 1. 배경

sprite_gen의 `wan_backend.py`에는 동일 이미지의 이전 실패 이력을 읽어,
빈발하는 이슈를 WAN 모델의 negative 프롬프트에 자동 추가하는 기능이 있었음.

이 기능이 engine에 미구현 상태여서, 동일 이미지를 반복 생성할 때
이전 실패 경험이 반영되지 않고 동일한 실패를 반복하는 문제가 있었음.

---

## 2. 동작 원리

```
생성 시작
  ↓
validation_stats.txt 파싱 (load_history)
  ↓
해당 이미지의 이전 실패 이력에서 이슈 빈도 집계
(metric 이슈 + AI 이슈 모두 포함)
  ↓
2회 이상 발생한 이슈만 필터링
  ↓
ISSUE_NEGATIVE_MAP에서 중국어 negative 프롬프트 추출
  ↓
base_negative에 자동 추가
  ↓
이후 모든 attempt에서 강화된 negative 적용
```

### 예시

이전 10회 시도에서 `ghosting` 8회, `unnatural_movement` 6회 발생 시:

```
base_negative = "analysis.negative + BG_NEGATIVE"
  + 이력 강화: "残影，鬼影，半透明残像，画面闪烁，细节闪烁，身体变形，身体拉伸，身体扭曲，动作不自然，轨迹突变"
```

---

## 3. ISSUE_NEGATIVE_MAP (12개 이슈)

| 이슈 | negative 프롬프트 (중국어) | 비고 |
|------|--------------------------|------|
| ghosting | 残影，鬼影，半透明残像，画面闪烁，细节闪烁 | |
| unnatural_movement | 身体变形，身体拉伸，身体扭曲，动作不自然，轨迹突变 | |
| character_inconsistency | 风格改变，纹理重建，角色外观变化，颜色失真 | |
| background_color_change | 背景变色，背景变暗，背景变灰 | |
| frame_escape | 画面外移动，超出边界 | |
| no_return_to_origin | 动作不回归，姿势偏移 | |
| speed_too_fast | 动作过快，快速移动，急速运动 | |
| flickering | 画面闪烁，亮度变化，闪烁不定 | |
| repeated_motion | 重复动作，动作循环不自然 | |
| no_motion | (빈 문자열) | positive 강화 대상 |
| too_slow | (빈 문자열) | positive 강화 대상 |
| speed_too_slow | (빈 문자열) | positive 강화 대상 |

---

## 4. 구현 파일

| 파일 | 변경 | 내용 |
|------|------|------|
| `retry_state.py` | 수정 | ISSUE_NEGATIVE_MAP 7→12개 확장 + LoopState에 `history_negative` 필드 추가 + `build_prompts()`에서 history_negative 반영 |
| `retry_logger.py` | 수정 | `load_history()` 추가 (정규식 기반 stats 파일 파싱) + `build_history_negative()` 추가 (빈도 집계 + negative 추출) |
| `retry_loop.py` | 수정 | `run()` 시작 시 `build_history_negative()` 호출 → `state.history_negative`에 주입 |

### 프롬프트 적용 순서 (LoopState.build_prompts)

```
positive = base_positive + adj_positive (AI 조정)
negative = base_negative + history_negative (이력 강화) + adj_negative (AI 조정)
```

---

## 5. validation_stats.txt 파싱

### 파일 형식 (sprite_gen과 동일)

```
[2026-03-10 12:19:56] IMAGE: frog_01
  attempt 1: metric_fail  | ghosting                    [AI: unnatural_movement] → ai_adjust
  attempt 2: metric_fail  | ghosting                    [AI: character_inconsistency] → action_switch
  attempt 3: metric_fail  | no_motion, too_slow         → seed_retry
  ---
```

### 파싱 결과 (load_history)

```python
{
    "images": {
        "frog_01": {
            "attempts": [
                {"issues": ["ghosting"], "ai_issues": ["unnatural_movement"]},
                {"issues": ["ghosting"], "ai_issues": ["character_inconsistency"]},
                {"issues": ["no_motion", "too_slow"], "ai_issues": []},
            ]
        }
    },
    "total_attempts": 3
}
```

### 빈도 집계 → negative 생성

```
ghosting: 2회 → "残影，鬼影，半透明残像，画面闪烁，细节闪烁"
unnatural_movement: 1회 → (2회 미만, 스킵)
no_motion: 1회 → (빈 문자열, 스킵)
```

---

## 6. 터미널 로그 출력

```
[Animate] start: frog_01
  [이력] 기존 영상 7개 발견 → attempt 8부터 시작
  [이력 강화] 이전 7회 실패 기반 negative: 残影，鬼影，半透明残像，画面闪烁，细节闪烁...
```

이력이 있지만 빈도 2회 이상 이슈가 없는 경우:
```
  [이력] 이전 2회 기록 (빈도 2회 이상 이슈 없음 → 스킵)
```

---

## 7. 기존 이력 호환

engine의 `artifacts/animate/motion/validation_stats.txt`에
sprite_gen의 기존 이력(281줄, 19장 102회)이 이미 복사되어 있으므로,
engine에서 생성 시작 시 이전 sprite_gen 실패 이력도 자동 반영됨.

---

## 8. 검증

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success |
| 200줄 제약 | 0건 위반 (retry_loop 200, retry_logger 199, retry_state 79) |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
