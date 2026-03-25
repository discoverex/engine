# KEYFRAME_ONLY Lottie 프레임 레이트 불일치 수정 보고서

> 작성일: 2026-03-20
> 브랜치: wan/test
> 대상 파일: `lottie_baker_transform.py`, `engine_server.py`, `engine_server_helpers.py`

---

## 1. 문제

KEYFRAME_ONLY 모드에서 대시보드 **프리뷰 애니메이션**과 **내보낸 Lottie 파일**의 속도가 달랐음.

### 원인

| 항목 | 프리뷰 (CSS) | Lottie (수정 전) |
|------|-------------|-----------------|
| fps | 60fps (브라우저 requestAnimationFrame) | 16fps (모션 Lottie 기본값) |
| 이징 | CSS `cubic-bezier()` 정확 계산 | 단순 Lottie `i`/`o` 보간 포인트 근사 |
| 리샘플링 | 프레임별 연속 렌더링 | 희소 키프레임 간 Lottie 자체 보간 |

**결과**: 동일한 키프레임 데이터인데 프리뷰는 60fps 부드러운 CSS 애니메이션, Lottie는 16fps로 뚝뚝 끊기거나 이징 곡선이 달라 타이밍 불일치.

---

## 2. 수정 내용

### 2.1 lottie_baker_transform.py — 핵심 수정 (83줄 → 134줄)

#### A) KEYFRAME_ONLY 타임라인 확장

수정 전: 단일 프레임 Lottie(`total <= 1`)에서 키프레임 주입이 무시됨.

수정 후:

```python
_KF_FPS = 60  # match browser requestAnimationFrame

if total <= 1:
    dur_ms = kf_data.get("duration_ms", 1500)
    fps = _KF_FPS
    total = max(2, round(dur_ms / 1000 * fps))
    result["fr"] = fps
    result["ip"] = 0
    result["op"] = total
    for layer in result.get("layers", []):
        layer["op"] = total
```

- `duration_ms`에서 총 프레임 수 계산 (예: 1500ms → 90프레임)
- fps를 **60**으로 설정하여 브라우저 프리뷰와 동일한 프레임 레이트
- 모든 기존 레이어의 `op`도 함께 확장

#### B) CSS cubic-bezier 정확 구현

수정 전: `EASING_MAP`에 단순 `i`/`o` 보간 좌표만 저장 → Lottie 자체 보간에 의존.

수정 후: Newton's method로 CSS `cubic-bezier(x1,y1,x2,y2)` 곡선을 정확히 계산.

```python
_BEZIER = {
    "linear":      (0.0,  0.0, 1.0, 1.0),
    "ease":        (0.25, 0.1, 0.25, 1.0),
    "ease-in":     (0.42, 0.0, 1.0, 1.0),
    "ease-out":    (0.0,  0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
}

def _cubic_bezier(t, x1, y1, x2, y2):
    # Newton's method: B_x(u) = t → u → B_y(u)
```

- 5종 표준 CSS 이징 + `ease` 추가
- 브라우저 `animation-timing-function`과 수학적으로 동일한 결과

#### C) 프레임별 리샘플링

수정 전: 희소 키프레임(예: 3개)을 Lottie `i`/`o` 보간에 맡김 → 곡선 불일치.

수정 후: `_resample_css()`로 모든 프레임에 대해 보간값을 미리 계산.

```python
def _resample_css(keyframes, total, easing):
    # 각 프레임에 대해 CSS cubic-bezier 이징 적용
    # translateX, translateY, rotate, scaleX, scaleY, opacity 모두 리샘플
```

- 키프레임 세그먼트별 local_t 계산 → 이징 적용 → 보간
- 결과: Lottie에 프레임 단위 값이 직접 들어가므로 Lottie 플레이어 보간 의존 제거

### 2.2 engine_server.py — KEYFRAME_ONLY 시 단일 프레임 Lottie 생성

```python
# classify API에서 KEYFRAME_ONLY 판정 시
lottie_result = build_keyframe_only_lottie(
    img, stem, DIR_MOTION, _orchestrator.format_converter,
)
```

- 비디오 없이 원본 이미지 1장으로 단일 프레임 Lottie 생성
- 대시보드에서 즉시 키프레임 에디터 진입 가능

### 2.3 engine_server_helpers.py — `build_keyframe_only_lottie()` 추가

```python
def build_keyframe_only_lottie(img, stem, motion_dir, converter):
    # 원본 이미지 → RGBA 변환 → 투명 프레임 1장 저장
    # format_converter.convert([frame], preset="original", fps=1)
    # → 단일 프레임 Lottie JSON 생성
```

---

## 3. 수정 전후 비교

### KEYFRAME_ONLY 흐름

| 단계 | 수정 전 | 수정 후 |
|------|---------|---------|
| classify 응답 | `lottie_path: null` | 단일 프레임 Lottie 경로 반환 |
| Lottie fps | 16 (모션 기본값) | **60** (브라우저 동일) |
| 키프레임 베이크 | 타임라인 1프레임 → 주입 실패 | `duration_ms` → 타임라인 자동 확장 |
| 이징 | Lottie 자체 보간 (불일치) | CSS cubic-bezier 정확 계산 (일치) |
| 프리뷰 vs 내보내기 | 속도/이징 불일치 | **동일** |

### 이징 정확도

| 이징 | 수정 전 | 수정 후 |
|------|---------|---------|
| linear | 근사 | 정확 |
| ease-in | `i/o` 좌표 근사 | Newton's method 정확 |
| ease-out | 근사 | 정확 |
| ease-in-out | 근사 | 정확 |
| ease | 미지원 | 추가 |

---

## 4. 기술 상세

### 왜 60fps인가

- 브라우저 CSS 애니메이션은 `requestAnimationFrame` 기준 **60fps**로 렌더링
- 대시보드 프리뷰가 CSS `@keyframes`로 동작하므로 60fps
- Lottie도 60fps로 맞추면 프레임 단위 1:1 대응 → 타이밍 완전 일치
- Lottie 플레이어(lottie-web 등)는 60fps를 네이티브로 지원

### 왜 리샘플링인가

Lottie의 `i`/`o` 베지어 보간은 CSS `cubic-bezier()`와 수학적으로 다른 방식.
Lottie는 값 공간(value space)에서 보간하고, CSS는 시간 공간(time space)에서 보간.
이 차이를 없애려면 모든 프레임의 값을 미리 계산하여 Lottie에 직접 넣어야 함.

---

## 5. 영향 범위

| 파일 | 변경 |
|------|------|
| `lottie_baker_transform.py` | 83줄 → 134줄 (이징 엔진 + 리샘플링 추가) |
| `engine_server.py` | classify API에 keyframe-only Lottie 생성 추가 |
| `engine_server_helpers.py` | `build_keyframe_only_lottie()` 함수 추가 |

### 변경 없음

| 항목 | 이유 |
|------|------|
| `lottie_baker.py` | `bake_keyframes()` 진입점 시그니처 동일 |
| `FormatConversionPort` | 포트 인터페이스 변경 없음 |
| `KeyframeGenerationPort` | 키프레임 생성 로직 변경 없음 |
| MOTION_NEEDED 경로 | 모션 Lottie는 이미 영상 기반이므로 영향 없음 |

---

## 6. 검증

| 항목 | 결과 |
|------|------|
| 프리뷰 vs Lottie 속도 | 일치 확인 |
| ease-in-out 이징 곡선 | 브라우저 CSS와 동일 |
| KEYFRAME_ONLY 타임라인 | duration_ms 기반 자동 확장 동작 |
| MOTION_NEEDED 경로 | 기존 동작 유지 (회귀 없음) |
| 200줄 제약 | 134줄 ✅ |
