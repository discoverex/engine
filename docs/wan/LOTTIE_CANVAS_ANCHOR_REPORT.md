# Lottie 캔버스 확장 + 좌상단 기준점 구현 리포트

> 작성일: 2026-03-23
> 커밋: b0afeae (캔버스 확장), 30ebd13 (좌상단 기준점)
> 브랜치: wan/test

---

## 배경

Lottie 변환 시 두 가지 문제가 있었다:

1. **캔버스 = 이미지 크기**로 투명 배경 여백이 없어 키프레임 애니메이션 시 잘림 발생
2. **기준점(anchor)이 이미지 중앙**으로, 외부 시스템에서 좌상단 기준 좌표가 필요할 때 변환이 필요

## 변경 1: 투명 배경 캔버스 확장 (b0afeae)

### 이전

```
캔버스 = 이미지 크기 (44×74)
┌──────┐
│ 나비 │  여백 없음 → 키프레임 이동 시 잘림
└──────┘
```

### 현재

```
캔버스 = 이미지 × 1.5 (66×110)
┌────────────────┐
│    (투명)      │
│  ┌──────┐      │
│  │ 나비 │      │  이미지 크기 유지, 캔버스만 확장
│  └──────┘      │
│    (투명)      │
└────────────────┘
```

### 구현

`format_converter.py`의 `_save_lottie()`에 `canvas_padding` 파라미터 추가:

```python
# 캔버스 = 이미지 × padding
cw = int(iw * canvas_padding) // 2 * 2  # 캔버스 가로
ch = int(ih * canvas_padding) // 2 * 2  # 캔버스 세로
# 이미지(asset)는 원본 크기(iw, ih) 유지
```

| 항목 | 값 |
|------|-----|
| `canvas_padding` | 1.5 (기본값, 변경 가능) |
| 이미지(asset) 크기 | 원본 유지 |
| 캔버스 크기 | 이미지 × 1.5 |

---

## 변경 2: 기준점을 이미지 좌상단(left-top)으로 변경 (30ebd13)

### 이전

```
anchor = [iw/2, ih/2]  (이미지 중앙)
position = [cx, cy]    (캔버스 중앙)
→ rotate/scale 시 이미지 중앙 기준
```

### 현재

```
anchor = [0, 0]              (이미지 좌상단)
position = [img_x, img_y]    (캔버스 내 이미지 좌상단 좌표)
→ rotate/scale 시 이미지 좌상단 기준

캔버스 (66×110)
┌────────────────┐
│                │
│  ★┌──────┐    │  ★ = anchor [0,0] = 기준점
│  │ 나비  │    │  position = [11, 18] (img_x, img_y)
│  └──────┘    │
│                │
└────────────────┘
```

### 구현

**format_converter.py** — 프레임 레이어:

```python
# 이미지 좌상단 위치 계산
img_x = (cw - iw) / 2
img_y = (ch - ih) / 2

# 레이어 설정
"p": {"a": 0, "k": [img_x, img_y, 0]},  # position = 이미지 좌상단
"a": {"a": 0, "k": [0, 0, 0]},           # anchor = 이미지 좌상단
```

**lottie_baker_transform.py** — null 레이어:

```python
# 첫 번째 이미지 레이어의 position에서 기준점 추출
img_layer = next((ly for ly in layers if ly.get("ty") == 2), None)
if img_layer:
    lp = img_layer["ks"]["p"]["k"]
    cx, cy = float(lp[0]), float(lp[1])  # 이미지 좌상단 = 변환 기준
```

---

## 좌표 체계 요약

| 좌표 | 값 | 설명 |
|------|-----|------|
| 캔버스 크기 | `cw × ch` | 이미지 × 1.5 |
| 이미지 크기 | `iw × ih` | 원본 유지 |
| 이미지 좌상단 | `(img_x, img_y)` | `((cw-iw)/2, (ch-ih)/2)` |
| anchor | `[0, 0, 0]` | 이미지 좌상단 |
| position | `[img_x, img_y, 0]` | 캔버스 내 이미지 좌상단 |
| rotate/scale 축 | 이미지 좌상단 | anchor 기준 |
| translate | 이미지 좌상단 기준 이동 | position에 가산 |

## 변경 파일

| 파일 | 내용 |
|------|------|
| `adapters/outbound/animate/format_converter.py` | canvas_padding, anchor=[0,0], position=[img_x, img_y] |
| `adapters/outbound/animate/lottie_baker_transform.py` | null 레이어 기준점을 이미지 좌상단에서 추출 |

---

## 변경 3: 캔버스 480×480 고정 (1eff692)

canvas_padding 비율 방식에서 **고정 480×480 캔버스**로 변경.

```python
# format_converter.py
canvas_size: int = 480  # 고정

cw, ch = canvas_size, canvas_size
img_x = (cw - iw) / 2   # 이미지 좌상단 x
img_y = (ch - ih) / 2   # 이미지 좌상단 y
```

```
캔버스 480×480 (투명 배경)
┌──────────────────────────────┐
│                              │
│        ★┌──────┐            │  ★ = anchor [0,0] (이미지 좌상단)
│        │ 나비  │            │  position = [218, 203]
│        │44×74  │            │  이미지 크기 유지
│        └──────┘            │
│                              │
└──────────────────────────────┘
```

---

## 변경 4: 두 경로 모두 적용 확인 (8a55735)

Lottie 생성 경로가 2개 있으며, 둘 다 동일한 `_save_lottie()` 함수를 거친다.

### 경로 1: KEYFRAME_ONLY (모션 불필요)

```
이미지 분류 → keyframe_only 판정
  → build_keyframe_only_lottie()
    → converter.convert([단일 프레임], preset="original", fps=1)
      → _save_lottie()  ← 캔버스 480, anchor [0,0] 적용 ✅
```

### 경로 2: MOTION_NEEDED (모션 + 키프레임)

```
WAN 모션 생성 → 배경 제거 → 투명 프레임
  → api_select_video()
    → converter.convert_with_opts(frames, fps, max_size)
      → _save_lottie()  ← 캔버스 480, anchor [0,0] 적용 ✅
```

### lottie_info 응답 통일

두 경로 모두 동일한 형식으로 응답:

```json
{
  "width": 480,
  "height": 480,
  "original_width": 60,
  "original_height": 83,
  "fps": 16,
  "frame_count": 64,
  "file_size_mb": 1.2
}
```

| 파일 | 수정 내용 |
|------|----------|
| `engine_server_helpers.py` | `build_keyframe_only_lottie` 응답에 `original_width/height` 추가, `width/height`를 Lottie JSON에서 읽도록 수정 |

---

## 변경 5: 캔버스를 원본 비율 × 배수로 변경 (9102a94)

정사각형 고정(480×480)에서 **원본 비율 유지 × 배수** 방식으로 변경.

### 이전

```python
canvas_size: int = 480
cw, ch = canvas_size, canvas_size  # 항상 정사각형
```

### 현재

```python
canvas_scale: float = 4.0
cw = int(iw * canvas_scale) // 2 * 2  # 원본 비율 유지
ch = int(ih * canvas_scale) // 2 * 2
```

### 예시

| 원본 (배경 제거 후) | 배율 | 캔버스 | 비율 |
|-------------------|------|--------|------|
| 44×74 | 4.0 (기본) | 176×296 | 44:74 유지 |
| 44×74 | 2.0 | 88×148 | 44:74 유지 |
| 44×74 | 6.0 | 264×444 | 44:74 유지 |
| 100×100 | 4.0 | 400×400 | 1:1 유지 |

배율을 변경해도 **항상 동일한 비율**이 유지되므로 이미지가 찌그러지지 않는다.

### 변경 파일

| 파일 | 내용 |
|------|------|
| `format_converter.py` | `canvas_size` → `canvas_scale` 파라미터 변경 |

---

## 변경 6: Lottie 프레임 bbox 크롭 + 원본 크기 리사이즈 (abba6fa)

### 문제

투명 프레임이 480×480 그대로 유지되어, `max_size=91`(원본 max 변)을 적용하면 480→90으로 전체가 축소되어 **90×90 정사각형**이 됨. 원본 비율(91:72)이 깨짐.

### 해결

`_save_lottie()`에서 alpha 채널 기반 오브젝트 bbox를 자동 감지 → 크롭 → 원본 크기로 리사이즈.

```
이전: 480×480 → max_size=91 → 90×90 (비율 깨짐)
현재: 480×480 → bbox 크롭 316×249 → max_size=91 → 91×71 (비율 유지)
```

### `_detect_object_bbox()` 함수

```python
def _detect_object_bbox(img, threshold=10):
    # RGBA alpha > threshold인 영역의 bbox 반환
    # → (x0, y0, x1, y1) 또는 None
```

### 업스케일링 경로 확인

업스케일은 **원본 이미지에서 직접** 진행됨:

```
원본 (91×72)
  → max(91,72) = 91 < 200 (임계값) → 업스케일 대상
  → factor = 480 × 0.65 / 91 = 3.43배
  → Real-ESRGAN 4x: 91×72 → 364×288
  → 요청 배율과 모델 배율 차이 → Lanczos 리사이즈: 312×247
  → 480×480 캔버스에 중앙 배치
```

| 단계 | 크기 |
|------|------|
| 원본 | 91×72 |
| Real-ESRGAN 4x | 364×288 |
| 요청 배율 리사이즈 | 312×247 |
| 캔버스 배치 | 480×480 |
| WAN 모션 생성 | 480×480 |
| 배경 제거 | 480×480 (투명) |
| bbox 크롭 | 316×249 |
| 원본 크기 리사이즈 | 91×71 |
| Lottie 캔버스 (4배) | 364×284 |

---

## 전체 변경 이력

| 커밋 | 내용 |
|------|------|
| b0afeae | 캔버스 확장 (canvas_padding=1.5) |
| 30ebd13 | 기준점을 이미지 좌상단(left-top)으로 변경 |
| 1eff692 | 캔버스 480×480 고정 |
| 8a55735 | KEYFRAME_ONLY 경로도 동일 적용 확인 |
| 9102a94 | **원본 비율 × 배수 (canvas_scale=4.0)** |
| abba6fa | bbox 크롭 + 원본 크기 리사이즈 (90×90 → 91×71) |
| f258f2f | 전체 프레임 통합 bbox — 모션 중 날개 잘림 방지 |

---

## 변경 7: 전체 프레임 통합 bbox — 모션 중 잘림 방지 (f258f2f)

### 문제

첫 프레임만으로 bbox를 결정하여, 날개가 크게 펼쳐진 프레임에서 **오른쪽이 잘림**.

```
첫 프레임 bbox: (82,85)~(397,333) = 316×249
전체 통합 bbox: (26,61)~(433,366) = 408×306
  → 오른쪽 36px, 아래 33px, 왼쪽 56px, 위 24px 잘림 발생
```

### 해결

`_detect_object_bbox(first_frame)` → `_detect_union_bbox(all_frames)`

모든 프레임의 alpha 채널을 검사하여 **모션 전체 범위를 포함하는 통합 bbox**를 사용.

```python
def _detect_union_bbox(frames, threshold=10):
    # 전체 프레임의 alpha > threshold 영역을 합산
    # → 모션 범위 전체를 포함하는 bbox 반환
```

### 결과

| 항목 | 이전 | 현재 |
|------|------|------|
| bbox 결정 | 첫 프레임만 (316×249) | 전체 프레임 통합 (408×306) |
| 오른쪽 잘림 | 36px | 0px |
| 이미지 크기 (max_size=91) | 91×71 | 91×68 (통합 비율) |
| 캔버스 (4배) | 364×284 | 364×272 |

## 테스트

247 passed, 7 skipped, 0 failed
