# 프로그레스 바 실시간 표시 수정 보고서

> 작성일: 2026-03-19
> 브랜치: wan/test
> 관련 커밋: `1325c3f` (초기), `ce6f417` (/queue 시도), `3c100f3` (WebSocket 최종)

---

## 1. 문제

대시보드에 프로그레스 바 UI는 있지만, 진행률이 0%에서 갱신되지 않는 상태.

---

## 2. 원인 추적

| 시도 | 방법 | 결과 |
|------|------|------|
| 1차 (`1325c3f`) | ComfyUI `/progress` HTTP GET | **실패** — 해당 엔드포인트 미존재 (404) |
| 2차 (`ce6f417`) | ComfyUI `/queue` HTTP GET → 노드 수 추정 | **실패** — queue_running 데이터에 step/total 정보 없음 |
| 3차 (`3c100f3`) | ComfyUI **WebSocket `/ws`** 연결 | **성공** — 실시간 progress 메시지 수신 |

### ComfyUI 진행률 제공 방식

| 방식 | 엔드포인트 | step/total 제공 |
|------|-----------|----------------|
| HTTP `/progress` | 미존재 | - |
| HTTP `/queue` | 존재 | ❌ 실행 여부만 |
| HTTP `/history` | 존재 | ❌ 완료 후만 |
| **WebSocket `/ws`** | **존재** | **✅ 실시간** |

ComfyUI는 KSampler 실행 중 WebSocket으로 다음 메시지를 전송:
```json
{"type": "progress", "data": {"value": 15, "max": 30, "prompt_id": "..."}}
```

---

## 3. 최종 구현

### 아키텍처

```
ComfyUI WebSocket /ws
    ↓ {"type":"progress","data":{"value":15,"max":30}}
comfyui_progress.py (백그라운드 스레드)
    ↓ 실시간 업데이트
ComfyUIClient.current_progress = {"step":15, "total":30}
    ↓ 5초 간격 폴링
engine_server /api/status → {"progress":{"step":15,"total":30,"percent":50}}
    ↓
dashboard.html 프로그레스 바 → ████████████░░░░░░░░ 15/30 steps (50%)
```

### 파일 변경

| 파일 | 변경 |
|------|------|
| `comfyui_progress.py` | **신규** (46줄) — WebSocket 연결 + progress 메시지 수신 스레드 |
| `comfyui_client.py` | 수정 — wait_for_completion에서 WS 리스너 시작/종료 관리 |
| `engine_server_helpers.py` | 수정 — HTTP 호출 제거, 클래스 변수에서 읽기 |

### comfyui_progress.py 동작

```python
def start_ws_progress(base_url, stop_flag, progress_ref):
    # WebSocket 연결: ws://127.0.0.1:8188/ws?clientId=progress
    # 메시지 수신 루프:
    #   type=="progress" → progress_ref 업데이트
    #   type=="executing" + node==None → 완료, 루프 종료
    # stop_flag["stop"]=True → 외부에서 종료 신호
```

### wait_for_completion 변경

```
변경 전:
  while True:
    history 폴링 → 완료 확인
    /queue 폴링 → 진행률 추정 (부정확)
    sleep

변경 후:
  WS 리스너 시작 (백그라운드 스레드)
  while True:
    history 폴링 → 완료 확인
    (progress는 WS에서 자동 갱신)
    sleep
  finally:
    WS 리스너 종료
```

---

## 4. 프론트엔드 표시

생성 중:
```
생성 중... (45초, 0/7개 영상)
████████████░░░░░░░░░░░░░░  15/30 steps (50%)
```

완료 시: 프로그레스 바 숨김, "완료 (N개)" 뱃지 표시.

---

## 5. 검증

| 항목 | 결과 |
|------|------|
| ruff check | All checks passed |
| 200줄 제약 | 0건 위반 (comfyui_client 182, comfyui_progress 46) |
| 전체 테스트 | **234 passed, 8 skipped, 0 failed** |
