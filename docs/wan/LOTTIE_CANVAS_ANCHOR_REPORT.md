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

## 테스트

247 passed, 7 skipped, 0 failed
