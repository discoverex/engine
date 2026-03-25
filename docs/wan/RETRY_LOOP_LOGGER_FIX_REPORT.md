# RetryLoop logger 미정의 버그 수정 보고서

**작성일**: 2026-03-21
**심각도**: HIGH (모션 생성 전체 차단)

## 증상

- ComfyUI 모션 생성 시 웹페이지에 `name 'logger' is not defined` 에러 표시
- 파이프라인 진행 불가

## 원인

`retry_loop.py`에서 `import logging`은 존재하나 `logger` 인스턴스를 생성하지 않음.

```python
# 기존 코드 (retry_loop.py)
import logging   # ← import만 존재
# logger = logging.getLogger(__name__)  ← 누락
```

`logger`를 참조하는 3개 지점에서 `NameError` 발생:

| 행 | 코드 | 용도 |
|----|------|------|
| 56 | `logger.info("  [이력] 기존 영상 %d개 발견 ...")` | 기존 영상 오프셋 로그 |
| 91 | `logger.warning(f"[Retry] generation failed: {e}")` | 생성 실패 경고 |
| 164 | `logger.warning(f"[ActionSwitch] failed: {e}")` | 액션 전환 실패 경고 |

## 수정 (1파일, 1줄)

**`src/discoverex/application/use_cases/animate/retry_loop.py`**

```python
# 29행에 추가
logger = logging.getLogger(__name__)
```

## 검증

- import 확인: `from discoverex.application.use_cases.animate.retry_loop import RetryLoop` → OK
- 테스트: 225 passed, 8 skipped, 0 failed
- 200줄 제약: 189줄 (준수)
