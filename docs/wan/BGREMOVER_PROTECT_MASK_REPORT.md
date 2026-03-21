# BG 제거 원본 마스크 보호 기능 구현 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 커밋: 207791a

---

## 1. 문제

나비 이미지의 배경을 제거할 때, 날개의 흰색 영역이 흰색 배경과 함께 삭제됨.
flood-fill 알고리즘이 배경 흰색과 날개 흰색을 구분하지 못하여 발생.

```
원본 나비: 날개에 흰색 패턴 포함
   ↓ BG 제거 (flood-fill, tolerance=50)
결과: 날개 흰색 부분이 투명 처리 → 날개 손상
```

---

## 2. 해결 방법 — 원본 이미지 마스크 보호

원본 입력 이미지(`_processed.png`)는 깨끗한 흰색 배경이므로,
flood-fill로 캐릭터 실루엣을 정확하게 추출 가능.
이 실루엣을 **보호 마스크**로 사용하여, 캐릭터 내부 픽셀은 배경 제거에서 제외.

### 동작 흐름

```
1. 비디오 경로에서 원본 이미지 탐색
   KakaoTalk_..._processed_a7.mp4 → _a7 제거 → KakaoTalk_..._processed.png

2. 원본 이미지에서 보호 마스크 생성
   flood-fill → 테두리 연결 배경 검출 → 반전(~) → 캐릭터 영역 = True

3. 각 프레임 배경 제거 시 보호 적용
   bg_mask = flood-fill 배경 검출 (기존)
   bg_mask &= ~protect  ← 보호 영역은 배경에서 제외
   → 캐릭터 내부 흰색 보존
```

### 비교

```
수정 전:
  배경(흰색) + 날개(흰색) → 둘 다 투명 처리 → 날개 손상

수정 후:
  배경(흰색) → 투명 처리
  날개(흰색) → 보호 마스크에 의해 보존 → 날개 유지
```

---

## 3. 구현

### 수정 파일

`src/discoverex/adapters/outbound/animate/bg_remover.py` (97줄 → 133줄)

### 추가된 함수

```python
def _build_protect_mask(video, bg_color, tolerance) -> np.ndarray | None:
    # 1. 비디오 stem에서 _a{N} 제거 → 원본 이미지 경로 추론
    # 2. 원본 이미지 로드
    # 3. flood-fill로 배경 영역 검출
    # 4. 반전 → 캐릭터 영역 = True (보호 대상)
```

### 수정된 함수

```python
def _remove_bg_frame(frame, bg_color, tolerance, protect=None):
    # 기존: bg_mask = flood-fill 배경
    # 추가: if protect is not None: bg_mask &= ~protect
    # → 보호 영역 내 픽셀은 배경으로 판정하지 않음
```

### FfmpegBgRemover.remove() 변경

```python
def remove(self, video, fps=16):
    # 기존: frames → bg_color → remove per frame
    # 추가: protect = _build_protect_mask(video, bg_color, tolerance)
    #       → 각 프레임에 protect 전달
```

---

## 4. 포트 인터페이스 영향

`BackgroundRemovalPort.remove(video, fps)` 시그니처 **변경 없음**.
보호 마스크는 어댑터 내부에서 자동으로 원본 이미지를 탐색하여 생성.
원본 이미지가 없으면 기존 동작(보호 없는 flood-fill)으로 fallback.

---

## 5. 검증

| 항목 | 결과 |
|------|------|
| 보호 마스크 생성 | ✅ 캐릭터 영역 4% (10,558 / 230,400 픽셀) |
| ruff check | All checks passed |
| mypy strict | Success |
| 200줄 제약 | ✅ (133줄) |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |

---

## 6. 원본 이미지 탐색 규칙

```
비디오: {stem}_a{N}.mp4
원본:   {stem}.png (같은 디렉토리)

예:
  KakaoTalk_20260319_145244697_processed_a7.mp4
  → _a7 제거 → KakaoTalk_20260319_145244697_processed
  → .png 추가 → KakaoTalk_20260319_145244697_processed.png
```

원본 이미지가 없으면 경고 로그 출력 후 보호 없이 기존 방식으로 처리.
