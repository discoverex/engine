# 메모리 최적화 보고서

**작성일**: 2026-03-21
**대상 환경**: RAM 16GB + VRAM 6GB (WSL2)

## 문제

- 비디오 생성 1회 완료 후 다음 시도 전환 시점에서 WSL이 OOM으로 종료
- `animate_comfyui_wan22` 프로필 사용 시 텍스트 인코더 CPU 오프로드(~6.4GB RAM) + 프레임 배열 누적으로 16GB RAM 한계 초과

## 원인 분석

### 메모리 누적 지점

| 단계 | 원인 | 시도당 누적 |
|------|------|------------|
| Numerical Validator | `extract_frames()` → numpy float32 배열이 검증 후 미해제 | ~24MB |
| AI Validator | 비디오 로드 후 미해제 | 가변 |
| Retry Loop | 시도 간 Python GC 미호출 → 이전 시도 데이터가 불확정 시점에 수거 | 누적 |

### 최악의 경우 (7회 시도)

```
텍스트 인코더 CPU 오프로드:  ~6.4GB
ComfyUI 프로세스:            ~1.5GB
Engine 프로세스:             ~0.5GB
프레임 배열 누적 (7회):      ~168MB
WSL 커널 + 오버헤드:         ~1.5GB
────────────────────────────────
합계:                        ~10GB+ (스왑 없으면 OOM 위험)
```

## 적용된 수정 (3파일)

### 1. `numerical_validator.py`

- `import gc` 추가
- 9개 메트릭 계산 완료 후 `del frames` + `gc.collect()`
- 효과: numpy 프레임 배열(~24MB) 즉시 해제, 피크 메모리 항상 ~24MB로 유지

### 2. `retry_loop.py`

- `import gc` 추가
- 매 시도(pass/fail) 처리 후 `gc.collect()` 호출
- 효과: 시도 간 Python GC 강제 실행으로 누적 방지

### 3. `retry_state.py`

- `RetryConfig`, `RetryResult` dataclass를 `retry_loop.py`에서 이동
- 사유: `retry_loop.py` 200줄 제약 준수를 위한 리팩터링
- `retry_loop.py`에서 re-import하므로 기존 import 경로 호환 유지

## 성능 영향

| 항목 | 수치 |
|------|------|
| RAM 절약 | ~144MB (7회 시도 기준) |
| 성능 저하 | `gc.collect()` ~10-50ms × 7회 = 최대 0.35초 |
| 비디오 생성 1회 소요 | ~4-5분 → 0.05초 추가는 무시 가능 |
| 기존 테스트 | 233 passed, 8 skipped, 0 failed |

## WSL 환경 권장 설정

### `.wslconfig` (필수)

파일 위치: `C:\Users\<사용자명>\.wslconfig`

```ini
[wsl2]
memory=14GB
swap=16GB
```

적용: `wsl --shutdown` 후 WSL 재시작

### 실행 명령어 (RAM 16GB + VRAM 6GB)

```bash
# 터미널 1: ComfyUI
cd ~/ComfyUI && source venv/bin/activate && python main.py --listen 0.0.0.0 --port 8188 --lowvram

# 터미널 2: Engine (WAN 2.2 5B 프로필)
cd ~/engine && export $(grep -v '^#' .env | xargs) && uv run discoverex serve --port 5001 --config-name animate_comfyui_wan22
```

## 프로필별 요구사양

| 프로필 | 모델 | VRAM | RAM (CPU 오프로드) |
|--------|------|------|--------------------|
| `animate_comfyui` | WAN 2.1 14B | ~12GB | ~6GB |
| `animate_comfyui_lowvram` | WAN 2.1 14B + CPU 오프로드 | ~8GB | ~14GB |
| `animate_comfyui_wan22` | WAN 2.2 5B + CPU 오프로드 | ~5.4GB | ~14GB |
