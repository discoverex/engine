# Lottie 원본 이미지 크기 자동 적용 리포트

> 작성일: 2026-03-23
> 커밋: 449bec0, 837e6c2
> 브랜치: wan/test

---

## 배경 및 문제

WAN 파이프라인은 소형 이미지를 업스케일 후 480×480 캔버스에 배치하여 모션을 생성한다. 이후 Lottie 변환 시에도 480×480 또는 슬라이더로 지정한 크기로 출력되어 **원본 이미지 크기와 무관한 Lottie가 생성**되는 문제가 있었다.

```
이전 흐름:
원본 (60×83) → 업스케일 → 480×480 WAN → Lottie 480×480 (또는 슬라이더 값)
                                         ↑ 원본 크기 정보 소실
```

## 해결

### 1. 원본 이미지 크기 보존

- `orchestrator.py`에서 전처리 전 원본 크기를 캡처하고 `AnimateResult.original_size`에 저장
- 원본 이미지를 `motion/` 폴더에 복사하여 이후 API에서 참조 가능

### 2. Lottie 변환 시 원본 크기 자동 적용

- `engine_server_extra.py`의 `select_video` API에 `_detect_original_size()` 추가
- 비디오 파일명에서 원본 이미지를 역추적하여 크기 감지
- `target_size` 미전송 시 원본 크기의 max 변을 사용

```
현재 흐름:
원본 (60×83) → 업스케일 → 480×480 WAN → Lottie 83px (원본 max 변)
                                         ↑ 원본 크기 자동 감지
```

### 3. 슬라이더 UI 제거

- 대시보드의 Lottie 크기 슬라이더(120~512px) 제거
- `target_size` 파라미터를 전송하지 않음 → 서버가 자동 결정
- 원본 이미지와 동일한 크기로 Lottie가 생성됨

## 변경 파일

| 파일 | 내용 |
|------|------|
| `application/use_cases/animate/orchestrator.py` | `original_size` 캡처, 원본 이미지 복사 |
| `adapters/inbound/web/engine_server_extra.py` | `_detect_original_size()`, 원본 크기 기반 Lottie 생성 |
| `adapters/inbound/web/dashboard.html` | Lottie 크기 슬라이더 제거, target_size 미전송 |

## API 응답 변경

`/api/select_video` 응답의 `lottie_info`에 원본 크기 정보 추가:

```json
{
  "lottie_info": {
    "width": 83,
    "height": 60,
    "original_width": 60,
    "original_height": 83,
    "fps": 16,
    "frame_count": 64,
    "duration_ms": 4000,
    "file_size_mb": 1.2
  }
}
```

## 원본 크기 감지 로직

`_detect_original_size(video_path)`:

```
비디오: name_processed_a8.mp4
  → stem: name_processed_a8
  → rsplit("_a", 1)[0]: name_processed
  → replace("_processed", ""): name
  → motion/name.png 탐색 → 원본 크기 반환
  → 없으면 (480, 480) 폴백
```
