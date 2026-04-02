# Lottie 내보내기 404 에러 수정 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test

---

## 1. 증상

대시보드에서 "통합 Lottie" 또는 "모션 Lottie" 버튼 클릭 시:
```
통합 내보내기 실패: lottie not found
```

서버 로그:
```
POST /api/export_combined  → 404
POST /api/export_lottie    → 404
```

Lottie 파일 자체는 정상 생성되어 존재함.

---

## 2. 원인

### 경로 중복 문제

`select_video` API 응답에서 `lottie_path`가 **절대경로**로 반환됨:
```
/home/snake2/engine/artifacts/animate/motion/...a7.json
```

그러나 프론트엔드의 `/api/files/` 호출에서 **상대경로**로 변환되어 `state.lottieData.lottie_path`에 저장:
```
artifacts/animate/motion/...a7.json
```

이 상대경로가 export API에 전달될 때, 서버 측 코드:
```python
lp = Path(lottie_path)           # "artifacts/animate/motion/...a7.json"
if not lp.is_absolute():         # True (상대경로)
    lp = output_dir / lottie_path  # output_dir = "artifacts/animate"
```

결과 경로:
```
artifacts/animate/artifacts/animate/motion/...a7.json
→ 경로 중복 → 파일 미존재 → 404
```

---

## 3. 수정

### `engine_server_helpers.py` — `resolve_lottie()` 함수 추가

3단계 경로 탐색으로 상대/절대 경로 모두 처리:

```python
def resolve_lottie(raw: str, output_dir: Path) -> Path | None:
    p = Path(raw)
    if p.is_absolute() and p.exists():   # 1. 절대경로
        return p
    cwd = Path.cwd() / raw
    if cwd.exists():                      # 2. CWD 기준 상대경로
        return cwd
    od = output_dir / raw
    if od.exists():                       # 3. output_dir 기준 상대경로
        return od
    return None
```

### `engine_server_extra.py` — export API에서 `resolve_lottie()` 사용

```python
# 수정 전
lp = Path(lottie_path)
if not lp.is_absolute():
    lp = output_dir / lottie_path

# 수정 후
lp = resolve_lottie(lottie_path, output_dir)
if not lp:
    return jsonify({"error": "lottie not found"}), 404
```

`export_combined`과 `export_lottie` 양쪽 모두 동일 적용.

---

## 4. 변경 파일

| 파일 | 변경 |
|------|------|
| `engine_server_helpers.py` | `resolve_lottie()` 함수 추가 (169 → 184줄) |
| `engine_server_extra.py` | `resolve_lottie` import + 2곳 호출 교체 (209 → 196줄) |

---

## 5. Lottie 파일 저장 경로 (참고)

```
~/engine/artifacts/animate/motion/{stem}_transparent/
  ├── {stem}.json            ← Lottie JSON
  ├── {stem}.apng            ← APNG
  ├── {stem}.webm            ← WebM
  ├── {stem}_frame_0000.png  ← 투명 프레임
  ├── {stem}_frame_0001.png
  └── ...
```

`select_video` API 호출 시 `bg_remover.remove()` → `format_converter.convert()` 순서로 생성.

---

## 6. 검증

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| mypy strict | Success |
| 200줄 제약 | extra 196줄, helpers 184줄 ✅ |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
