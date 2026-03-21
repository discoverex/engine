# lottie_info null 참조 에러 수정 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 커밋: 7a84c65

---

## 1. 증상

```
[18시 19분 22초] Error: Cannot read properties of undefined (reading 'file_size_mb')
```

대시보드에서 이미지 분류 또는 비디오 선택 시 JS 에러 발생.

---

## 2. 원인

sprite_gen의 `/api/classify`와 `/api/select_video`는 `lottie_info` 객체를 반환:
```json
{
  "lottie_info": {
    "fps": 16,
    "frame_count": 24,
    "duration_ms": 1500,
    "file_size_mb": 1.0
  }
}
```

engine의 동일 API는 `lottie_info: null`을 반환. 대시보드 JS가 null 체크 없이 `.file_size_mb`에 접근하여 에러 발생.

| API | sprite_gen | engine (수정 전) |
|-----|-----------|-----------------|
| `/api/classify` | lottie_info 객체 반환 | `null` |
| `/api/select_video` | lottie_info 객체 반환 | 필드 자체 없음 |

---

## 3. 수정 내용

### 3.1 dashboard.html — null-safe 체크 (3곳)

**classify 응답 (라인 583):**
```javascript
// 수정 전
data.lottie_info.file_size_mb.toFixed(1)

// 수정 후
const li = data.lottie_info;
li && li.file_size_mb ? li.file_size_mb.toFixed(1) : ''
```

**select_video 응답 (라인 1229, 1240):**
```javascript
// 수정 전
data.lottie_info.file_size_mb.toFixed(1)
info.file_size_mb.toFixed(1)

// 수정 후
const li4 = data.lottie_info;
li4 ? li4.file_size_mb.toFixed(1) : ''
if (li4) { /* info 표시 */ }
```

### 3.2 engine_server_extra.py — /api/select_video에 lottie_info 추가

```python
lottie_info = {
    "fps": fps,
    "frame_count": len(transparent.frames),
    "duration_ms": round(len(transparent.frames) / fps * 1000),
    "width": 0,
    "height": 0,
    "file_size_mb": round(lp.stat().st_size / (1024 * 1024), 1),
}
```

---

## 4. 검증

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
| JS 에러 | 수정 완료 (null-safe) |
