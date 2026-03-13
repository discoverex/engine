# Prefect Engine Debug Status

## Scope
- 이 문서는 현재 디버그 진행 상태 메모다.
- 운영 계약의 SSOT는 `docs/engine-prefect-registration/` 이다.
- 특히 아래 두 문서를 우선 기준으로 본다.
  - `docs/engine-prefect-registration/README.md`
  - `docs/engine-prefect-registration/runtime-auth-and-env.md`

## Resume From Here
- 현재 작업 브랜치:
  - `codex/discoverex-engine-run-wip`
- 현재 기준 커밋:
  - `7028346e3861af067c5c77624e848a53caeb259e`
- 워크트리 상태:
  - 이 문서(`PREFECT_ENGINE_DEBUG_STATUS.md`)만 수정 중일 수 있음
  - `.prefect-engine-artifacts/` 는 로컬 실행 산출물이며 추적 대상 아님
- 이 문서를 읽은 다음 바로 봐야 할 파일:
  - `src/discoverex/orchestrator_contract/launcher.py`
  - `src/discoverex/adapters/inbound/cli/main.py`
  - `src/discoverex/application/flows/run_engine_job.py`
  - `src/discoverex/application/services/execution_preparer.py`

## Known Run Matrix
### Known bad runs
- `b3eff397-b659-4501-a8ae-9fce4ddf8bd0`
  - state: `Failed`
  - purpose: real GPU spec first validation
  - proved:
    - initial Hydra import blocker는 이미 지나감
    - child engine Prefect API blocker도 이미 지나감
    - 하지만 `bg://dummy` 입력은 SDXL inpaint path와 호환되지 않음

### Known misleading run
- `1657c316-6748-4c66-b43d-6fd3e1b3ad11`
  - state: `Completed`
  - purpose: prompt 기반 spec으로 재실행
  - proved:
    - top-level Prefect flow는 완료 가능
    - 그러나 child execution이 `inline + local` 로 축소됨
    - 따라서 운영 의미의 worker-contract success로 보면 안 됨

## Do Not Regress
- 다시 깨지면 안 되는 것:
  - `discoverex.flows.subflows.generate_v1_compat` import locate 실패
  - child engine의 Prefect API 직접 호출
  - `real-generate-sdxl-gpu.json` 의 `bg://dummy` 사용
- 유지해야 하는 현재 보장:
  - `just test` 통과
  - targeted pytest 통과
  - 상위 Prefect deployment 진입 및 child launcher 실행 가능

## Current Contract Snapshot
- 공개 Prefect flow 이름은 `disoverex-engine-flow` 이다.
- 공개 deployment 이름은 `discoverex-engine-job` 이다.
- 외부 공개 entrypoint는 `prefect_flow.py:run_job_flow` 이다.
- deployment source는 HTTPS Git URL을 사용해야 한다.
  - `https://github.com/discoverex/engine.git`
- child engine runtime은 정상 실행 시 Prefect API를 직접 호출하지 않아야 한다.
  - 근거: `docs/engine-prefect-registration/runtime-auth-and-env.md`
- durable engine artifact는 worker-managed output-directory contract를 따라야 한다.
  - 근거: `docs/engine-prefect-registration/artifact-persistence-contract.md`

## Root Causes Confirmed
이전 상태 문서에 있던 Hydra 가설은 일부만 맞았고, 실제 확인된 원인은 아래 두 가지다.

### 1) Hydra target import 실패의 실제 원인
- 표면 에러:
  - `InstantiationException: Error locating target 'discoverex.flows.subflows.generate_v1_compat'`
- 실제 원인:
  - `discoverex.flows.subflows` import 시 먼저 `discoverex.flows.__init__` 가 실행된다.
  - 기존 `src/discoverex/flows/__init__.py` 가 repo root 모듈 `prefect_flow` 를 eager import 하고 있었다.
  - worker처럼 `PYTHONPATH=src` 중심으로 로드되는 환경에서는 `prefect_flow.py` 가 import path에 없을 수 있어 여기서 먼저 깨진다.
- 재현:
  - repo root 밖의 임시 디렉터리에서 `PYTHONPATH=/path/to/repo/src python -c "import discoverex.flows.subflows"` 로 재현됨

### 2) child engine의 Prefect API 직접 호출
- 증상:
  - 내부 generate/verify subflow가 다시 Prefect API에 붙으려 하면서 실패
  - 예: `Failed to reach API at https://prefect-api.discoverex.qzz.io/api/`
- 실제 원인:
  - worker/로컬 셸의 Prefect 설정이 child engine으로 흘러 들어갔다.
  - Prefect 3는 단순 env 삭제만으로는 부족하고, profile/default setting에 잡힌 API URL을 계속 사용할 수 있다.
- SSOT 정합성:
  - `runtime-auth-and-env.md` 에 따라 정상 engine 실행은 Prefect API 직접 호출이 필요 없다.

## Fixes Applied
- `src/discoverex/flows/__init__.py`
  - `prefect_flow` eager import 제거
  - 내부 subflow import가 repo root top-level module에 의존하지 않게 수정
- `src/discoverex/orchestrator_contract/launcher.py`
  - child env에서 `PREFECT_API_URL` 을 빈 문자열로 강제
  - `PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true` 기본 주입
  - `PREFECT_LOGGING_TO_API_ENABLED=false` 기본 주입
  - worker 전용 env가 child에 직접 남지 않도록 정리 유지
- 테스트 추가
  - `tests/test_flows_engine.py`
    - repo root가 `sys.path` 에 없어도 `discoverex.flows.subflows` import 성공 검증
  - `tests/test_orchestrator_launcher.py`
    - child env에 Prefect API 직접 연결 설정이 남지 않는지 검증
- `infra/register/job_specs/real-generate-sdxl-gpu.json`
  - `bg://dummy` 기반 asset_ref 입력 제거
  - prompt 기반 real GPU generate payload로 교체

## Additional Test Suite Repairs
플로우 수정과 별개로 `just test` 기준 기존 실패 2건도 함께 정리했다.

- `src/discoverex/application/contracts/execution/schema.py`
  - `JobSpec.engine_run` 호환 property 복구
- `tests/test_architecture_constraints.py`
  - `src/discoverex/adapters/outbound/models/sdxl_final_render.py` line-count 예외 목록 반영

## Validation Completed
### Targeted tests
- `uv run pytest -q tests/test_flows_engine.py tests/test_prefect_flows.py tests/test_orchestrator_launcher.py`
- 결과:
  - pass

### Full local test command
- `just test`
- 결과:
  - `169 passed, 6 skipped`

### End-to-end local flow path
다음 경로를 더미 generate 설정으로 실제 완료까지 확인했다.

- `prefect_flow.py:run_job_flow`
- child launcher
- `discoverex generate`
- 내부 generate Prefect subflow

확인 결과:
- 상태: `approved`
- 생성 산출물:
  - scene json 생성됨
  - execution config 생성됨
- 예시 산출물 경로:
  - `.prefect-engine-artifacts/run-8zj8cabc/scenes/scene-171f4132fee8/v-20260312144634/scene.json`
  - `.prefect-engine-artifacts/run-8zj8cabc/execution/generate/a1122e7a7f95/resolved_execution_config.json`

## Remote Worker Validation Reassessment
원격 worker run을 다시 뜯어보면, 이전에 적어둔 “성공”은 운영 의미의 성공이 아니었다.

핵심은 아래다.

- 상위 Prefect flow run은 `Completed` 였다.
- 하지만 child engine은 worker contract를 유지하지 않고 `local/inline` 경로로 재포장되어 실행됐다.
- 그래서 MinIO durable artifact, worker artifact upload contract, worker runtime mode, observable subflow execution이 기대대로 동작했다고 볼 수 없다.

즉 현재 상태는:

- 초기 Hydra import 문제는 해결됨
- child engine의 Prefect API 직접 호출 문제는 해결됨
- 그러나 worker execution contract는 아직 깨져 있음

### Failed validation run
- flow run id:
  - `b3eff397-b659-4501-a8ae-9fce4ddf8bd0`
- 결과:
  - `Failed`
- 실패 원인:
  - `object inpaint requires a real source image path`
- 해석:
  - 초기 Prefect/Hydra 문제는 통과했지만, `real-generate-sdxl-gpu.json` 이 `bg://dummy` 를 사용하고 있어서
    SDXL inpaint 경로와 맞지 않았다.

### Successful validation run
- flow run id:
  - `1657c316-6748-4c66-b43d-6fd3e1b3ad11`
- deployment:
  - `discoverex-engine-job`
- 결과:
  - `Completed`
- launcher payload summary:
  - `status=approved`
  - `scene_id=scene-2ce33689d20f`
  - `version_id=v-20260312150428`
  - `scene_json=/tmp/tmps5ixsl_yprefect/engine-codex-discoverex-engine-run-wip/.prefect-engine-artifacts/run-haty28_e/scenes/scene-2ce33689d20f/v-20260312150428/scene.json`
  - `execution_config=/tmp/tmps5ixsl_yprefect/engine-codex-discoverex-engine-run-wip/.prefect-engine-artifacts/run-haty28_e/execution/generate/1163aeb77509/resolved_execution_config.json`

이 run에서 실제로 확인된 사실:
- `discoverex.flows.subflows.generate_v1_compat` import 에러는 재발하지 않았다.
- child engine의 Prefect API 직접 호출 문제는 재발하지 않았다.
- prompt 기반 입력으로 최종 payload는 `approved` 까지 갔다.

하지만 이 run을 운영 성공으로 볼 수 없는 이유가 있다.

## Newly Confirmed Structural Problem
### 문제 요약
worker가 넘긴 `repo + worker runtime` job spec이 child engine 안에서 사라지고,
CLI 경로를 거치며 `inline + local runtime` job spec으로 다시 생성된다.

그 결과:
- MinIO artifact store 경로가 활성화되지 않는다.
- worker-managed durable artifact contract가 지켜지지 않는다.
- MLflow server / storage / metadata 같은 worker override가 구조적으로 보존되지 않는다.
- 내부 generate subflow는 worker contract 하의 observable engine run이 아니라 child process 내부의 local Prefect flow로 돌아간다.

### 증거 1: 성공 run payload가 이미 `inline`
성공 run `1657c316-6748-4c66-b43d-6fd3e1b3ad11` 의 worker 로그 `launcher payload summary` 에서:

- `run_mode=inline`
- `scene_json=/tmp/.../.prefect-engine-artifacts/...`
- `execution_config=/tmp/.../.prefect-engine-artifacts/...`

즉 worker repo 실행의 산출물이라기보다 child process 로컬 디렉터리 결과가 그대로 반환되었다.

### 증거 2: CLI가 항상 `JobRuntime(mode=\"local\")` 를 강제
`src/discoverex/adapters/inbound/cli/main.py`

- `_run_command()` 에서 `build_inline_job_spec(...)` 호출
- 그리고 `runtime=JobRuntime(mode=\"local\")` 를 하드코딩

즉 launcher가 `discoverex generate ...` 를 호출하는 순간,
원래 `ORCH_JOB_INPUTS_JSON` 에 담긴 worker runtime 정보는 버려진다.

### 증거 3: inline job spec 자체가 `run_mode=inline`
`src/discoverex/application/flows/run_engine_job.py`

- `build_inline_job_spec()` 가 명시적으로 `run_mode: "inline"` payload를 생성
- runtime 기본값도 `JobRuntime(mode=\"local\")`

### 증거 4: 실행 준비 상태도 `local fast-path`
실패 run `b3eff397-b659-4501-a8ae-9fce4ddf8bd0` 의 error payload 안 `preparation` 에서:

- `mode: "local"`
- `actions: ["fast-path"]`

이 값은 `src/discoverex/application/services/execution_preparer.py` 의 local branch와 정확히 일치한다.
즉 worker runtime mode가 child 안에서 보존되지 않았다는 직접 증거다.

### 증거 5: MinIO 저장 증거가 없음
성공 run 로그에서 durable artifact는 모두 `/tmp/.../.prefect-engine-artifacts/...` 로만 보인다.

보이지 않는 것:
- `s3://...` object URI
- worker artifact upload 결과
- MinIO 저장 완료 로그
- worker output-directory manifest upload 결과

SSOT 기준으로 보면 이건 미완성이다.

## Why This Matters
현재 상태에서는 “상위 flow가 Completed” 여도 아래를 보장하지 못한다.

- scene bundle이 MinIO에 durable 하게 저장되었는지
- worker artifact contract가 실제로 실행되었는지
- tracker/storage adapter가 worker mode 설정으로 동작했는지
- retry/resume/checkpoint semantics가 worker contract와 일치하는지
- subflow의 실행/관측이 control-plane에서 의미 있게 남는지

즉 지금은 top-level Prefect run 성공과 실제 engine contract 성공이 분리되어 있다.

## Root Cause Analysis
실행 경로를 단계별로 보면 문제가 더 명확하다.

1. Prefect deployment는 `prefect_flow.py:run_job_flow` 를 실행한다.
2. `prefect_flow.py` 는 child process로 `discoverex.orchestrator_contract.launcher` 를 실행한다.
3. launcher는 `ORCH_JOB_INPUTS_JSON` 에서 worker runtime payload를 읽는다.
4. 그러나 launcher는 최종적으로 `discoverex generate|verify|animate` CLI를 호출한다.
5. CLI는 다시 `build_inline_job_spec(..., runtime=JobRuntime(mode="local"))` 를 만들고 `run_engine_job()` 을 호출한다.
6. 이 시점에서 원래 worker runtime mode, run_mode, env semantics가 사라진다.

즉 현재 launcher의 최종 hop이 잘못되었다.

launcher는 현재:
- worker contract payload를 읽는 역할은 맞게 수행하지만
- 그 payload를 보존한 채 engine을 실행하지 않고
- CLI compatibility layer를 통해 local inline execution으로 축소해 버린다.

## Correctness Assessment
### 해결된 것
- `discoverex.flows.subflows.generate_v1_compat` import 오류
- child engine의 Prefect API 직접 호출 문제
- `real-generate-sdxl-gpu.json` 의 `bg://dummy` 입력 문제

### 아직 해결되지 않은 것
- worker runtime contract 보존
- MinIO durable artifact 저장 확인
- worker-managed artifact manifest 업로드 확인
- worker mode adapters의 실제 사용 보장
- 운영 의미의 subflow observability

## Required Fix Direction
필수 수정 방향은 아래와 같다.

1. launcher가 CLI를 경유하지 않도록 변경
- `discoverex generate|verify|animate` 호출을 제거
- 원래 `ORCH_JOB_INPUTS_JSON` payload를 유지한 채 engine entry를 직접 호출해야 한다.

2. CLI의 local-inline 강제 분리
- 현재 CLI는 로컬 개발용 compatibility wrapper로만 남기고
- worker launcher 경로에서는 사용하지 않게 해야 한다.

3. worker runtime 보존
- `run_mode=repo`
- `inputs.runtime.mode=worker`
- runtime extras / extra_env
- job_spec.env
를 child engine 내부까지 잃지 않도록 유지해야 한다.

4. artifact contract 검증 추가
- worker output-directory manifest 생성
- MinIO upload 결과
- 필요 시 MLflow tag/object URI 기록
를 테스트/운영 검증에 포함해야 한다.

## Next Fix Target
가장 먼저 고칠 대상은 `launcher -> CLI -> inline/local` 축소 구간이다.

현재 잘못된 경로:
1. `prefect_flow.py`
2. `discoverex.orchestrator_contract.launcher`
3. `discoverex generate`
4. CLI가 `build_inline_job_spec(..., JobRuntime(mode="local"))`
5. `run_engine_job()`

고쳐야 할 방향:
1. launcher가 `ORCH_JOB_INPUTS_JSON` 의 worker payload를 파싱
2. 그 payload를 직접 `run_engine_job()` 또는 전용 entry module에 전달
3. CLI compatibility wrapper는 worker path에서 배제

주의:
- 이미 해결된 `PREFECT_API_URL` 격리 로직은 되돌리면 안 된다.
- 이미 해결된 `discoverex.flows.__init__` import 문제도 되돌리면 안 된다.

## Acceptance Criteria
수정 완료 판정은 아래를 모두 만족해야 한다.

1. 상위 Prefect flow run이 `Completed`
2. child payload 또는 로그에서 `run_mode=inline` 이 보이지 않음
3. child payload 또는 로그에서 `preparation.mode=local` / `actions=["fast-path"]` 가 보이지 않음
4. MinIO 또는 worker artifact upload 결과가 확인됨
5. worker-managed artifact manifest 처리 결과가 확인됨
6. `scene_json` / `execution_config` 가 단순 `/tmp/.../.prefect-engine-artifacts/...` 로만 끝나지 않음
7. 필요 시 MLflow tag/object URI 또는 worker artifact metadata로 durable location 확인 가능

## Exact Repro Steps
### Local regression checks
```bash
just test
UV_CACHE_DIR="$PWD/.cache/uv" uv run pytest -q tests/test_flows_engine.py tests/test_prefect_flows.py tests/test_orchestrator_launcher.py
```

### Deployment inspection
```bash
UV_CACHE_DIR="$PWD/.cache/uv" PYTHONPATH="$PWD/infra/register" uv run python - <<'PY'
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import DeploymentFilter, DeploymentFilterName
from prefect.settings import PREFECT_API_URL, temporary_settings
from register_orchestrator_job import _client_httpx_settings

with temporary_settings(updates={PREFECT_API_URL: 'https://prefect-api.discoverex.qzz.io/api'}):
    with get_client(sync_client=True, httpx_settings=_client_httpx_settings()) as client:
        rows = client.read_deployments(
            deployment_filter=DeploymentFilter(name=DeploymentFilterName(any_=['discoverex-engine-job'])),
            limit=20,
        )
        for row in rows:
            print(row.id, row.name, row.entrypoint, row.pull_steps)
PY
```

### Submit real GPU spec
```bash
UV_CACHE_DIR="$PWD/.cache/uv" PYTHONPATH="$PWD/infra/register" uv run python - <<'PY'
import json
from pathlib import Path
from register_orchestrator_job import submit_job_spec

job_spec = json.loads(Path('infra/register/job_specs/real-generate-sdxl-gpu.json').read_text())
print(submit_job_spec(
    job_spec=job_spec,
    prefect_api_url='https://prefect-api.discoverex.qzz.io/api',
    deployment='discoverex-engine-job',
    job_name=job_spec.get('job_name'),
))
PY
```

### Poll a flow run
```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run python infra/register/check_flow_run_status.py <flow_run_id>
```

## Remaining Work
- launcher의 CLI 경유 실행을 제거하고 worker contract 보존 경로로 수정해야 한다.
- 그 뒤 다시 real GPU run을 실행해서 아래를 재검증해야 한다.
  - run_mode가 더 이상 `inline` 으로 축소되지 않는지
  - preparation mode가 `local fast-path` 가 아닌 worker semantics를 반영하는지
  - scene/execution config/artifact manifest가 worker contract에 따라 durable upload 되는지
  - MinIO 또는 worker artifact upload 결과가 실제로 남는지
- deployment refresh API는 여전히 `500 Internal Server Error` 가 한 번 발생했다.
  - 기존 `discoverex-engine-job` deployment가 동일 브랜치를 가리켜 실행 검증 자체는 가능했다.
  - 다만 control-plane 측 별도 이슈로 추적이 필요하다.

## Reference Files
- `prefect_flow.py`
- `src/discoverex/flows/__init__.py`
- `src/discoverex/orchestrator_contract/launcher.py`
- `src/discoverex/adapters/inbound/cli/main.py`
- `src/discoverex/application/flows/run_engine_job.py`
- `src/discoverex/application/services/execution_preparer.py`
- `infra/register/job_specs/real-generate-sdxl-gpu.json`
- `src/discoverex/application/flows/engine_entry.py`
- `tests/test_flows_engine.py`
- `tests/test_orchestrator_launcher.py`
- `docs/engine-prefect-registration/README.md`
- `docs/engine-prefect-registration/runtime-auth-and-env.md`
- `docs/engine-prefect-registration/artifact-persistence-contract.md`
