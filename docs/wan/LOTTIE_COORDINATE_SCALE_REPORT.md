# Lottie 키프레임 통합 리포트

**날짜**: 2026-03-22
**브랜치**: `wan/test`
**수정 파일**: `lottie_baker_transform.py`, `dashboard.html`

---

## 문제

웹 대시보드 프리뷰 대비 내보낸 Lottie 파일에서 품질 격차 발생:

1. **움직임 크기 불일치** — CSS 프리뷰보다 Lottie에서 이동 거리가 다름
2. **프레임 끊김** — 다양한 원인으로 모션/키프레임 끊김 발생
3. **LP0017 오류** — Lottie 뷰어에서 precomp asset의 `"fr"` 필드 경고
4. **방향 전환 시 멈춤** — per-segment bezier easing으로 keyframe 경계에서 정지
5. **속도 차이** — 키프레임이 전체 모션 길이에 매핑되어 느리게 재생
6. **프레임 짤림** — 캔버스 범위를 벗어나는 이동 시 콘텐츠 클리핑

---

## 끊김 원인 분석 히스토리

### 1차: fr=60 + round() ip/op + precomp (끊김 + LP0017)

- precomp asset에 `"fr": 60` → LP0017 경고
- `round()` 매핑 → 64프레임이 240슬롯에 3~4프레임 불균등 hold
- 241개 프레임별 사전계산 → 불필요하게 무거움

### 2차: fr=16 + bezier (여전히 끊김)

- 뷰어가 `setSubframe` 미사용 시 16fps 정수 프레임으로만 렌더링
- bezier 보간도 16fps 해상도로만 평가됨

### 3차: fr=60 + float ip/op + precomp (여전히 끊김)

원인 분리 테스트(A~D) 결과:

| 테스트 | 구조 | fr | 결과 |
|--------|------|-----|------|
| A. 직접 레이어 | 이미지 1장 | 16 | 부드러움 |
| B. 직접 레이어 | 이미지 1장 | 60 | **가장 부드러움** |
| C. 프리컴프+래퍼 | 이미지 1장 | 16 | 부드러움 |
| D. 프리컴프+래퍼 | 64장 base64 PNG | 60 | **끊김** |

**원인**: 프리컴프 + 64장 이미지 → 매 프레임 precomp 재합성 오버헤드

### 4차: 직접 레이어 + per-layer animated transform (끊김)

64개 레이어에 각각 animated p/r/s/o → 256개 animated 속성 → 렌더 과부하

### 5차: null parent + fr=60/16 (구조는 OK, 추가 문제 발견)

- null(ty=3) 1개에 transform, 64 이미지 레이어를 parent로 연결
- 추가 테스트(F~I) 결과: **null parent + 480x480 캔버스에서 부드러움 확인**
- 캔버스 확장(578x856) 시 SVG 뷰포트 증가로 프레임 드롭

### 6차: fr=48(16x3) 정수배 + linear bezier (움직임 부드러움 달성)

- fr=48: `setSubframe` 없이도 48fps 렌더링
- 정수 배수(3x): 모든 프레임 정확히 3프레임 hold, 끊김 없음
- **per-segment bezier → linear**: 방향 전환 시 멈춤 해결
  - CSS animate()는 global easing + keyframe 간 linear 보간
  - per-segment ease-in-out은 각 경계에서 감속→정지→가속 발생

### 7차: duration_ms 기반 타이밍 + 좌표 스케일링 보정

- **속도**: keyframe t값을 `duration_ms`에 매핑 (전체 모션 길이가 아닌)
- **스케일링**: `t_scale = canvas / preview_object_size` (실제 슬라이더 값 사용)

---

## 최종 통합 Lottie 구조

```
fr=48 (16×3 정수배)
null layer (ty=3): animated p/r/s/o, linear bezier, duration_ms 기반 타이밍
64 image layers: static transforms, parent=null, 각 3프레임 hold
캔버스: 480×480 (원본 유지, 확장 없음)
```

### 구조적 제한

- **프레임 짤림**: 캔버스(480x480)가 콘텐츠와 동일 크기이므로, 큰 이동 시 가장자리 클리핑 발생.
  이는 Lottie 포맷의 구조적 제한 — 캔버스 확장 시 SVG 렌더 부하로 프레임 드롭.
- **프리뷰와의 근본 차이**: 프리뷰는 CSS animate(GPU 60fps) + bodymovin(SVG 16fps)
  2-tier 렌더링. 단일 Lottie는 1-tier로 동일 품질 달성 불가.

---

## HTML 뷰어 내보내기 (프리뷰와 100% 동일)

통합 Lottie의 구조적 제한을 해결하기 위해 **HTML 뷰어 내보내기** 추가.
모션 Lottie + 키프레임 JSON을 단일 HTML 파일로 내보내기.

```html
<div id="outer">          <!-- CSS animate() — 60fps GPU 가속 -->
  <div id="inner"></div>  <!-- bodymovin — 16fps SVG 모션 -->
</div>
```

```javascript
// 모션 Lottie 로드
bodymovin.loadAnimation({
  container: inner, renderer: 'svg',
  loop: true, autoplay: true, animationData: lottieData,
});
// 키프레임 적용 (CSS animate = 프리뷰와 동일)
outer.animate(kfFrames, { duration, easing, iterations: 1, fill: 'none' });
```

**효과**:
- 프리뷰와 100% 동일한 2-tier 렌더링
- 짤림 없음 (스테이지가 오브젝트보다 큼)
- 끊김 없음 (CSS animate 60fps GPU 가속)
- 브라우저에서 바로 열어 확인 가능

---

## 내보내기 버튼 구성

| 버튼 | 내용 | 모션 | 키프레임 | 비고 |
|------|------|:---:|:---:|------|
| 📦 통합 Lottie | 단일 Lottie 파일 | O | O | 구조적 제한 있음 (짤림, 1-tier) |
| 🎬 모션 Lottie만 | 모션만 있는 Lottie | O | X | 키프레임 별도 적용 필요 |
| 🔑 키프레임 JSON | 키프레임 정보만 | X | O | CSS animate용 데이터 |
| 🌐 HTML 뷰어 | 모션+키프레임 합친 HTML | O | O | **프리뷰와 100% 동일** |

프론트엔드에서 모션 Lottie + 키프레임 JSON을 로드하여 CSS animate로 합쳐서
표시하는 것이 프리뷰와 동일한 품질을 달성하는 최적 방법.

---

## 검증

```
ruff check    : All checks passed
mypy strict   : Success (0 errors)
pytest        : 전체 통과 (animate/lottie/keyframe 34건 포함)
200줄 제약    : 149줄 ✅ (lottie_baker_transform.py)
```
