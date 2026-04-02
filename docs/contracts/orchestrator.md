# 오케스트레이터와 worker 계약

이 문서는 엔진이 Prefect-managed flow와 worker를 통해 실행될 때의 안정 경계를 정의한다. 운영 절차와 명령 예시는 [CLI 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/cli.md) 와 [런타임 가이드](/home/esillileu/discoverex/engine/docs/ops/runtime.md)에 둔다.

## 1. 공개 Prefect 엔트리포인트

루트 callable 표면:

- `prefect_flow.py:run_job_flow`
- `prefect_flow.py:run_generate_job_flow`
- `prefect_flow.py:run_verify_job_flow`
- `prefect_flow.py:run_animate_job_flow`
- `prefect_flow.py:run_combined_job_flow`

등록 flow 이름:

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

## 2. flow 역할

- `discoverex-engine-flow`: generic job-spec entrypoint
- `discoverex-generate-flow`: generate 전용 entrypoint
- `discoverex-verify-flow`: verify 전용 entrypoint
- `discoverex-animate-flow`: animate 전용 entrypoint
- `discoverex-combined-flow`: composite execution path

`discoverex-combined-flow` 는 `gen-verify` 를 explicit sequence로 분해할 수 있다.

## 3. 입력 계약

Prefect 레이어는 `job_spec_json` 을 받아 엔진 payload를 추출한다.

중요 상위 필드:

- `engine`
- `repo_url`
- `ref`
- `entrypoint`
- `inputs`
- `env`

엔진이 실제로 소비하는 부분은 `inputs` 아래 `EngineRunSpec` 이다. 자세한 payload shape는 [엔진 실행 계약](/home/esillileu/discoverex/engine/docs/contracts/engine-run.md)을 본다.

## 4. worker 런타임 환경

worker/runtime 레이어는 다음 환경값을 제공할 수 있다.

- `ORCH_JOB_INPUTS_JSON`
- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `MLFLOW_TRACKING_URI`

또한 다음 실행 메타데이터를 계산한다.

- flow run id
- attempt
- outputs prefix
- resolved settings snapshot

## 5. 아티팩트 책임 경계

worker는 orchestration 아티팩트를 항상 소유한다.

- `stdout.log`
- `stderr.log`
- `result.json`
- `artifacts.json`

엔진이 durable artifact를 만든다면:

- 파일은 `ORCH_ENGINE_ARTIFACT_DIR` 아래에 써야 한다
- manifest는 `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH` 에 기록해야 한다
- 업로드는 worker가 수행한다

## 6. MLflow 경계

엔진은 `MLFLOW_TRACKING_URI` 를 사용할 수 있다.

worker가 책임지는 항목:

- artifact upload
- uploaded object URI 기록
- MLflow artifact-link tagging

엔진은 다음에 직접 의존하지 않는다.

- MinIO credential 세부사항
- presign route
- backend MLflow host 내부 가정

## 7. 명령 호환성

공개 Prefect-facing 명령:

- `generate`
- `verify`
- `animate`

호환 alias:

- `gen-verify`
- `verify-only`
- `replay-eval`

현재 매핑:

- `gen-verify` -> `generate` 또는 explicit combined decomposition
- `verify-only` -> `verify`
- `replay-eval` -> `animate`

## 8. 현재 caveat

- `generate` 와 `verify` 는 현재 가장 안정적인 계약 경로다.
- `animate` 는 public contract 에 남아 있지만 내부 구현 기대치는 보수적으로 잡아야 한다.
- deployment 생성과 job submission 절차는 계약 자체가 아니라 운영 표면이며 [infra/ops](/home/esillileu/discoverex/engine/infra/ops) 와 운영 문서에 둔다.
