# MOTION_NEEDED 키프레임 FPS 업샘플링 리포트

**날짜**: 2026-03-22
**브랜치**: `wan/test`
**파일**: `src/discoverex/adapters/outbound/animate/lottie_baker_transform.py`

---

## 문제

MOTION_NEEDED 경로(모션 생성 → 키프레임 추가)에서 내보낸 Lottie 파일이 웹 프리뷰보다 프레임이 떨어져 보이는 현상.

### 원인

웹 대시보드 프리뷰는 2-tier 구조로 렌더링:

| 계층 | 방식 | FPS |
|------|------|-----|
| outer (키프레임) | CSS `Element.animate()` | ~60fps (requestAnimationFrame) |
| inner (모션) | bodymovin SVG | 16fps (Lottie fr 값) |

내보낸 Lottie는 모션 fps(16)를 키프레임 래퍼에도 그대로 적용:

- 키프레임 이징이 16fps로 샘플링 (4초 기준 64포인트)
- 프리뷰는 60fps로 보간 (4초 기준 ~240포인트)
- **3.75배 프레임 밀도 차이** → 끊겨 보이는 원인

### KEYFRAME_ONLY 경로는 이미 해결됨

`if total <= 1:` 조건에서 fps를 60으로 확장하고 Newton's method cubic-bezier로 리샘플링. 프리뷰와 동일한 품질.

---

## 수정 내용

`lottie_baker_transform.py` `apply_keyframes_to_lottie()` 함수에 `elif` 블록 추가 (93-107줄):

```python
# Multi-frame Lottie (MOTION_NEEDED): upsample to _KF_FPS so keyframe
# wrapper runs at 60 fps — matching the browser CSS animate() preview.
# Motion frames are held proportionally (e.g. each 16-fps frame spans
# ~3-4 frames at 60 fps), preserving the original playback duration.
elif fps < _KF_FPS:
    scale = _KF_FPS / fps
    new_total = round(total * scale)
    for layer in result.get("layers", []):
        layer["ip"] = round(layer.get("ip", 0) * scale)
        layer["op"] = round(layer.get("op", 0) * scale)
    result["fr"] = _KF_FPS
    result["ip"] = 0
    result["op"] = new_total
    fps = _KF_FPS
    total = new_total
```

### 동작 원리

1. 컴포지션 fps를 16 → 60으로 변경
2. 모션 프레임 레이어의 `ip`/`op`를 비례 확장 (각 프레임이 ~3-4 Lottie 프레임 동안 표시)
3. 키프레임 리샘플링이 60fps 해상도로 실행 (`_resample_css(keyframes, 240, easing)`)
4. 총 재생 시간 변동 없음 (64프레임/16fps = 240프레임/60fps = 4초)

---

## 수정 전 vs 수정 후 (4초 영상 기준)

| 항목 | 수정 전 | 수정 후 | 프리뷰 (CSS animate) |
|------|---------|---------|---------------------|
| 컴포지션 fps | 16 | **60** | ~60 |
| 키프레임 샘플 수 | 64 | **240** | ~240 |
| 이징 해상도 | 16fps | **60fps** | 60fps |
| 모션 프레임 수 | 64장 | 64장 (변동 없음) | 64장 |
| 총 재생 시간 | 4초 | 4초 (변동 없음) | 4초 |

---

## 검증

```
ruff check    : All checks passed
mypy strict   : Success (0 errors)
pytest        : 전체 통과 (animate/lottie/keyframe 34건 포함)
200줄 제약    : 149줄 ✅
```
