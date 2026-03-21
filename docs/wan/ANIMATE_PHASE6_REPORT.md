# Animate Integration — Phase 6 완료 보고서

> Phase 6: Flow 연결 & E2E
> 완료일: 2026-03-18

---

## 1. 작업 범위

ANIMATE_INTEGRATION_PLAN.md 섹션 8 Phase 6에 정의된 4개 항목:

25. `flows/subflows.py` — animate_stub → 실제 구현 교체
26. 통합 테스트: Dummy 어댑터로 전체 흐름
27. E2E 스모크: 실제 ComfyUI + Gemini 연동 → **미실행** (GPU 환경 없음)
28. Prefect 배포 검증 → **미실행** (Prefect worker 환경 없음)

---

## 2. 생성/수정된 파일

| 파일 | 라인 | 역할 |
|------|------|------|
| `src/discoverex/flows/subflows.py` (수정) | 125 | `animate_pipeline()` 함수 추가 |
| `conf/flows/animate/animate_pipeline.yaml` | 3 | Hydra flow 설정 (animate_pipeline 연결) |
| `tests/test_animate_flow.py` | 135 | Flow 레벨 통합 테스트 2건 |

### 2.1 subflows.py — animate_pipeline() 추가 (125L)

**원본 대응**: animate_stub() 교체

`animate_stub()`은 호환성을 위해 보존하고, 새 `animate_pipeline()` 함수를 추가:

```python
def animate_pipeline(*, args, config, execution_snapshot, execution_snapshot_path):
    orchestrator = build_animate_context(config.model_dump())
    result = orchestrator.run(Path(args["image_path"]))
    return {"status": ..., "video_path": ..., "action": ..., "mode": ..., "attempts": ...}
```

**동작 흐름**:
1. `args["image_path"]` 필수 검증 (없으면 즉시 실패)
2. `build_animate_context(config)` → AnimateOrchestrator 조립 (Hydra instantiate)
3. `orchestrator.run(image_path)` → AnimateResult
4. 결과를 engine 표준 payload dict로 변환하여 반환

**기존 subflow와의 일관성**:
- `generate_v1_compat`, `verify_v1_compat`, `animate_replay_eval`과 동일한 시그니처
- `(*, args, config, execution_snapshot, execution_snapshot_path) → dict[str, Any]`
- `execution_config` 키를 payload에 포함

### 2.2 animate_pipeline.yaml — Hydra flow 설정 (3L)

```yaml
# @package flows.animate
_target_: discoverex.flows.subflows.animate_pipeline
_partial_: true
```

기존 `stub.yaml`, `replay_eval.yaml`과 동일 패턴. `conf/animate.yaml`의 `flows/animate` 기본값을 `animate_pipeline`으로 변경하면 실제 파이프라인이 활성화됨.

**현재 `conf/animate.yaml`**: `flows/animate: stub` (기본값 유지)
**활성화 방법**: `-o flows/animate=animate_pipeline` 오버라이드 또는 `animate.yaml` 수정

### 2.3 test_animate_flow.py — Flow 통합 테스트 (135L, 2건)

| 테스트 | 검증 내용 |
|--------|----------|
| `test_missing_image_path` | `image_path` 누락 시 `status=failed` + 에러 메시지 |
| `test_full_flow_with_dummies` | mock으로 Dummy 오케스트레이터 주입 → 전체 흐름 `status=success`, `mode=motion_needed`, `attempts>=1` |

**mock 전략**: `@patch("discoverex.bootstrap.factory.build_animate_context")` — `animate_pipeline()` 내부 lazy import를 패치하여 Dummy 오케스트레이터 반환.

---

## 3. 미실행 항목

| 항목 | 이유 | 대안 |
|------|------|------|
| E2E 스모크 (ComfyUI + Gemini) | GPU 환경 + ComfyUI 서버 + Gemini API 키 필요 | Dummy 전체 흐름으로 로직 검증 완료. 실제 서비스 연동은 GPU 환경에서 별도 실행 |
| Prefect 배포 검증 | Prefect worker + work pool 필요 | `run_animate_job_flow()` 엔트리포인트는 기존 인프라에 이미 등록되어 있으며, flow 설정만 교체하면 동작 |

---

## 4. 설계 판단

### 4.1 animate_stub 보존

`animate_stub()`을 삭제하지 않고 보존. 이유:
- 기존 `conf/animate.yaml`이 `flows/animate: stub`을 기본값으로 참조
- 기존 테스트 `test_engine_job_v2_accepts_animate_without_required_args()`가 stub 동작에 의존
- 새 파이프라인은 Hydra 오버라이드로 활성화 (`-o flows/animate=animate_pipeline`)

### 4.2 config.model_dump() 전달

`build_animate_context()`에 `PipelineConfig` 대신 `config.model_dump()` dict를 전달. 이유:
- `PipelineConfig`에는 animate 전용 필드(`animate_adapters` 등)가 없음
- `build_animate_context()`는 내부에서 `AnimatePipelineConfig.model_validate(dict)`로 변환
- animate 설정은 Hydra 오버라이드로 주입되며, `PipelineConfig`의 extra fields로 전달됨

### 4.3 payload 형식

engine 표준 payload 키:
- `status`: "success" / "failed"
- `video_path`: 생성된 비디오 경로 (성공 시)
- `action`: VisionAnalysis의 action_desc
- `mode`: processing_mode 값 (keyframe_only / motion_needed)
- `attempts`: 시도 횟수
- `execution_config`: execution snapshot 경로

---

## 5. 검증 결과

| 검증 | 결과 |
|------|------|
| `ruff check` | All checks passed |
| `mypy` (2개 파일) | Success: no issues found |
| `pytest` (Phase 6 신규) | **2 passed** (0.88s) |
| `pytest` (전체) | **234 passed, 8 skipped, 0 failed** (11.33s) |
| 200라인 제약 | 모든 파일 200L 이하 (최대 135L) |

### 테스트 증가 추이

| Phase | 신규 테스트 | 누적 |
|-------|-----------|------|
| Phase 1 | 0 | 201 |
| Phase 2 | 0 | 201 |
| Phase 3 | 0 | 201 |
| Phase 4 | 30 | 231 |
| Phase 5 | 1 | 232 |
| Phase 6 | 2 | 234 |

---

## 6. 커밋 정보

- 커밋: `46439f7`
- 브랜치: `wan/test`
- 파일: 3개 (생성 2 + 수정 1), +178줄

---

## 7. 전체 Phase 1-6 완료 요약

| 항목 | 수치 |
|------|------|
| 총 신규 파일 | 50개 |
| 총 신규 코드 | +5,900줄 이상 |
| 총 테스트 | **234 passed, 8 skipped, 0 failed** |
| 신규 테스트 | 33건 |
| 200L 제약 위반 | 0건 |
| mypy strict 에러 | 0건 |
| HIGH 미해결 | **0건** |
| MEDIUM 미해결 | **0건** |
| LOW 미해결 | **3건** (ComfyUI 어댑터, 전처리 테스트, DummyFormatConverter) |

---

## 8. 남은 항목 (운영 환경에서 처리)

| # | 항목 | 시점 |
|---|------|------|
| 1 | ComfyUI 어댑터 구현 (~843줄, 5파일 분할) | GPU 환경에서 E2E 실행 시 |
| 2 | 전처리 단위 테스트 (PIL+scipy) | 테스트 보강 시 |
| 3 | E2E 스모크: ComfyUI + Gemini 실제 연동 | GPU + API 키 환경에서 |
| 4 | Prefect 배포 검증: `bin/cli prefect deploy-flow animate` | Prefect worker 환경에서 |
| 5 | `conf/animate.yaml` 기본값 stub → animate_pipeline 전환 | 운영 배포 시 |
