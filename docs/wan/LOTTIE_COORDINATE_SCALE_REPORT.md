# Lottie 좌표 스케일링 + 네이티브 Bezier 보간 리포트

**날짜**: 2026-03-22
**브랜치**: `wan/test`
**수정 파일**: `lottie_baker_transform.py`, `dashboard.html`

---

## 문제

웹 대시보드 프리뷰 대비 내보낸 Lottie 파일에서 세 가지 품질 격차 발생:

1. **움직임 크기가 작음** — CSS 프리뷰보다 Lottie에서 이동 거리가 눈에 띄게 작음
2. **프레임이 끊김** — MOTION_NEEDED 경로에서 모션 프레임 끊김 발생
3. **LP0017 오류** — Lottie 뷰어에서 precomp asset의 `"fr"` 필드 경고

두 문제 모두 KEYFRAME_ONLY / MOTION_NEEDED 경로에서 확인.

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

### 원인 2: FPS 업샘플링 부작용

초기 접근으로 모션 레이어를 16fps → 60fps로 업샘플링했으나 두 가지 문제 발생:

| 문제 | 원인 |
|------|------|
| **LP0017** | precomp asset에 `"fr": 60` 필드 추가 — Lottie 스펙에서 precomp에 `fr`은 비표준 |
| **프레임 끊김** | 64프레임을 240슬롯에 `round()` 매핑 → 3~4프레임 불균등 hold (50ms vs 67ms) |

실제 파일 분석 (`animation_combined (3).json`):

```
root:    fr=60, op=240, w=572, h=836
precomp: fr=60 ← LP0017 원인
         layer durations: [4,4,3,4,4,3,4,...] ← 불균등 → 시각적 끊김
wrapper: 241 keyframes ← 프레임별 사전계산 (불필요하게 무거움)
```

### 근본 원인

fps 업샘플링 + 프레임별 사전계산 접근 자체가 잘못됨.
Lottie는 자체 bezier 보간 엔진을 갖고 있으므로, 희소 키프레임 + bezier 이징을
전달하면 플레이어가 자체 디스플레이 레이트로 부드럽게 렌더링.

---

## 최종 수정 내용

### 1. Lottie 네이티브 Bezier 보간으로 전면 교체

fps 업샘플링과 프레임별 사전계산(`_resample_css`)을 제거하고,
CSS 키프레임을 Lottie 키프레임으로 직접 변환:

```python
# CSS cubic-bezier → Lottie out/in tangent 매핑
# CSS ease-in-out = cubic-bezier(0.42, 0, 0.58, 1)
# Lottie: o = {x: [0.42], y: [0]}, i = {x: [0.58], y: [1]}

# 희소 키프레임 (예: hop 8개)에 bezier 이징 첨부
for idx, kf in enumerate(keyframes):
    p = {"t": t, "s": [cx + tx, cy + ty, 0]}
    if idx < len(keyframes) - 1:
        p["e"] = [cx + ntx, cy + nty, 0]  # end value
        p["o"] = bez_o3                     # out tangent
        p["i"] = bez_i3                     # in tangent
```

**효과**:
- Lottie 플레이어가 bezier 곡선을 자체 디스플레이 레이트로 부드럽게 보간
- 프레임별 사전계산 불필요 → 파일 크기 대폭 감소

### 2. fr=60 업샘플링 + float ip/op (끊김 해결)

fr=16인 Lottie는 뷰어가 16fps로만 렌더링하여 프리뷰(60fps)와 차이 발생.
fr=60으로 올리되, 레이어 타이밍에 **정확한 float 값**을 사용:

```python
elif result.get("fr", 16) < _KF_FPS:
    scale = _KF_FPS / orig_fps  # 60/16 = 3.75
    for layer in result.get("layers", []):
        layer["ip"] = layer.get("ip", 0) * scale  # float, not round
        layer["op"] = layer.get("op", 0) * scale  # float, not round
    result["fr"] = _KF_FPS
```

| 방식 | Layer 0 | Layer 1 | Layer 2 | 프레임 hold |
|------|---------|---------|---------|-----------|
| round() (이전) | ip=0, op=4 | ip=4, op=8 | ip=8, op=11 | 4,4,**3** 불균등 |
| float (현재) | ip=0, op=3.75 | ip=3.75, op=7.5 | ip=7.5, op=11.25 | **모두 3.75** 균등 |

모든 모션 프레임이 정확히 62.5ms(=3.75/60) 동안 표시 — 원본 16fps와 동일한 타이밍.

### 3. precomp asset에서 `fr` 필드 제거 (LP0017 해결)

```python
# 수정 전 (LP0017 발생)
precomp = {"id": precomp_id, "layers": ..., "fr": fps, "nm": "motion_layers"}

# 수정 후 (LP0017 해결)
precomp = {"id": precomp_id, "layers": ..., "nm": "motion_layers"}
```

Lottie 스펙에서 precomp asset에 `fr`은 비표준 필드. root composition의 `fr`만 유효.

### 3. 좌표 스케일링 + 캔버스 확장 (유지)

CSS 픽셀 단위 translate 값을 Lottie 캔버스 비율로 스케일링:

```python
ref = kf_data.get("preview_object_size", 80)
t_scale = min(w, h) / ref  # 예: 480/80 = 6.0
# translate 값에 t_scale 적용 후 캔버스를 이동 범위만큼 확장
```

### 4. 프론트엔드: preview_object_size 전달 (유지)

```javascript
const exportKfData = {
  ...kfData,
  preview_object_size: parseInt(document.getElementById('kfObjScale').value) || 80,
};
```

---

## 수정 전 vs 최종 (모션 + 키프레임, 4초 64프레임)

| 항목 | 수정 전 (초기) | 중간 (round 업샘플) | 최종 (float + bezier) |
|------|--------------|-------------------|---------------------|
| root fr | 16 | 60 | **60** |
| root op | 64 | 240 | **240** |
| precomp fr | 없음 | 60 (LP0017) | **없음** |
| 모션 레이어 ip/op | 정수 균등 | round() 불균등 | **float 균등** |
| 프레임 hold | 62.5ms 균등 | 50~67ms 불균등 | **62.5ms 균등** |
| 키프레임 보간 | 64개 사전계산 | 241개 사전계산 | **8개 + bezier** |
| 보간 품질 | 16fps 뷰어 렌더 | 60fps 뷰어 렌더 | **60fps + bezier** |
| 파일 항목 수 | 64×4=256 | 241×4=964 | **8×4=32** |
| LP0017 | 없음 | 발생 | **없음** |
| 끊김 | 뷰어 16fps 렌더 | 3/4 불균등 | **없음** |
| 움직임 크기 | 12.5% (작음) | 스케일링 적용 | **스케일링 적용** |

---

## 끊김 원인 분석 히스토리

### 1차: fr=16 + bezier (끊김 지속)

fr=16으로 설정 시 Lottie 뷰어가 **16fps로만 렌더링**하여 프리뷰(60fps)와 차이 발생.
bezier 보간은 뷰어의 렌더 주기에 맞춰 평가되므로, fr=16이면 16fps 해상도로 보간됨.
프리뷰는 bodymovin이 `requestAnimationFrame`(60fps)으로 렌더링하여 부드러움.

### 2차: fr=60 + round() ip/op (3/4 끊김)

fr=60 업샘플링 시 `round()` 사용 → 64프레임이 240슬롯에 불균등 배분 (3 or 4프레임).
50ms/67ms 교차 → 시각적 마이크로 스터터.

### 최종: fr=60 + float ip/op + bezier (프리뷰와 동일)

float ip/op로 모든 모션 프레임이 정확히 3.75 Lottie 프레임 = 62.5ms.
bezier 키프레임은 뷰어가 60fps에서 부드럽게 보간.
프리뷰의 bodymovin(60fps) + CSS animate(60fps)와 구조적으로 동일.

---

## 경로별 적용 확인

| 수정 항목 | KEYFRAME_ONLY | MOTION_NEEDED |
|----------|:---:|:---:|
| Lottie 네이티브 bezier | O | O |
| fr=60 업샘플링 (float ip/op) | — (이미 fr=60) | O |
| precomp fr 제거 | O | O |
| 좌표 스케일링 | O | O |
| 캔버스 확장 | O | O |
| preview_object_size | O | O |

---

## 검증

```
ruff check    : All checks passed
mypy strict   : Success (0 errors)
pytest        : 전체 통과 (animate/lottie/keyframe 34건 포함)
200줄 제약    : 174줄 ✅
```
