# Lottie 좌표 스케일링 + FPS 업샘플링 리포트

**날짜**: 2026-03-22
**브랜치**: `wan/test`
**수정 파일**: `lottie_baker_transform.py`, `dashboard.html`

---

## 문제

웹 대시보드 프리뷰 대비 내보낸 Lottie 파일에서 두 가지 품질 격차 발생:

1. **움직임 크기가 작음** — CSS 프리뷰보다 Lottie에서 이동 거리가 눈에 띄게 작음
2. **프레임이 끊김** — MOTION_NEEDED 경로에서 키프레임 이징이 16fps로 샘플링됨

두 문제 모두 KEYFRAME_ONLY / MOTION_NEEDED 경로에서 확인 필요했음.

---

## 원인 1: 좌표계 불일치

### CSS 프리뷰

```
Stage: 800×600px
Object: 80px (kfObjScale 기본값)
translate(-60px) → 80px 대비 75% 이동 → 눈에 띄는 점프
```

### Lottie 내보내기 (수정 전)

```
Canvas: 480×480
translate(-60) → 480 대비 12.5% 이동 → 미세한 움직임
```

CSS `translate(Xpx)`는 스크린 픽셀 단위, Lottie position은 캔버스 단위.
동일한 값 `-60`이 프리뷰에서는 80px 대비 큰 이동이지만, Lottie에서는 480px 대비 미세한 이동.

### 원인 2: FPS 불일치 (MOTION_NEEDED 전용)

| 항목 | 프리뷰 (CSS animate) | Lottie (수정 전) |
|------|---------------------|-----------------|
| 키프레임 FPS | ~60fps | 16fps |
| 샘플 수 (4초) | ~240 | 64 |

---

## 수정 내용

### 1. 좌표 스케일링 + 캔버스 확장 (두 경로 공통)

`lottie_baker_transform.py`에 `_scale_translates()` 헬퍼 추가 (74-96줄):

```python
def _scale_translates(sampled, w, h, ref_size):
    if ref_size <= 0 or min(w, h) <= ref_size:
        return w, h
    t_scale = min(w, h) / ref_size  # 예: 480/80 = 6.0
    max_dx = max_dy = 0.0
    for s in sampled:
        s["translateX"] = s.get("translateX", 0.0) * t_scale
        s["translateY"] = s.get("translateY", 0.0) * t_scale
        max_dx = max(max_dx, abs(s["translateX"]))
        max_dy = max(max_dy, abs(s["translateY"]))
    if max_dx < 1 and max_dy < 1:
        return w, h
    pad_x = int(max_dx) + 1
    pad_y = int(max_dy) + 1
    return w + 2 * pad_x, h + 2 * pad_y
```

**동작**:
1. CSS 픽셀 단위 translate 값을 `min(w,h) / preview_object_size` 배율로 스케일링
2. 이동 범위만큼 캔버스를 양쪽으로 확장하여 콘텐츠 클리핑 방지
3. 프리컴프 anchor = 콘텐츠 중심(`w/2, h/2`), position = 확장 캔버스 중심(`canvas_w/2, canvas_h/2`)

### 2. FPS 업샘플링 (MOTION_NEEDED 전용)

`apply_keyframes_to_lottie()` 함수에 `elif` 블록 (122-132줄):

```python
elif fps < _KF_FPS:
    scale = _KF_FPS / fps          # 60/16 = 3.75
    new_total = round(total * scale) # 64 → 240
    for layer in result.get("layers", []):
        layer["ip"] = round(layer.get("ip", 0) * scale)
        layer["op"] = round(layer.get("op", 0) * scale)
    result["fr"] = _KF_FPS
    result["op"] = new_total
```

모션 프레임은 비례 확장(각 프레임이 ~3-4 Lottie 프레임 동안 표시), 키프레임 이징은 60fps 해상도로 리샘플링.

### 3. 프론트엔드: preview_object_size 전달

`dashboard.html` `exportCombinedLottie()` 수정:

```javascript
const exportKfData = {
  ...kfData,
  preview_object_size: parseInt(document.getElementById('kfObjScale').value) || 80,
};
```

사용자가 조절한 오브젝트 크기를 서버에 전달하여 정확한 스케일링 계산에 사용.

---

## 수정 전 vs 수정 후 (hop 60px, 480×480 캔버스, objSize=80)

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| translateY (Lottie) | -60 | **-360** (6x 스케일) |
| 캔버스 크기 | 480×480 | 480×**1202** (패딩 포함) |
| 80px 표시 시 실이동 | 10px | **24px** |
| FPS (MOTION_NEEDED) | 16 | **60** |
| 키프레임 샘플 (4초) | 64 | **240** |

---

## 경로별 적용 확인

| 수정 항목 | KEYFRAME_ONLY | MOTION_NEEDED |
|----------|:---:|:---:|
| FPS 60fps 확장 | O (기존 `if total<=1`) | O (신규 `elif fps<60`) |
| 좌표 스케일링 | O (`_scale_translates`) | O (동일) |
| 캔버스 확장 | O | O |
| preview_object_size | O | O |

---

## 검증

```
ruff check    : All checks passed
mypy strict   : Success (0 errors)
pytest        : 전체 통과 (animate/lottie/keyframe 34건 포함)
200줄 제약    : 186줄 ✅
```
