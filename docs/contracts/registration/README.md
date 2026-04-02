# 등록과 배포 계약

이 디렉터리는 이 저장소가 Prefect flow를 어떻게 공개하고, 등록된 실행이 어떤 파라미터와 런타임 경계를 갖는지 설명한다. 운영 절차는 [CLI 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/cli.md) 와 [Sweep 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/sweeps.md)를 본다.

구현 source of truth:

- [infra/ops](/home/esillileu/discoverex/engine/infra/ops)
- [infra/prefect](/home/esillileu/discoverex/engine/infra/prefect)
- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)

관련 계약 문서:

- [runtime-auth-and-env.md](/home/esillileu/discoverex/engine/docs/contracts/registration/runtime-auth-and-env.md)
- [artifact-persistence-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/artifact-persistence-contract.md)
- [worker-managed-output-directory-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/worker-managed-output-directory-contract.md)

## 1. 등록되는 flow kind

이 저장소는 목적 기반 Prefect deployment를 다음 flow kind로 등록한다.

- `combined`
- `generate`
- `verify`
- `animate`

공개 callable:

- `prefect_flow.py:run_job_flow`
- `prefect_flow.py:run_generate_job_flow`
- `prefect_flow.py:run_verify_job_flow`
- `prefect_flow.py:run_animate_job_flow`
- `prefect_flow.py:run_combined_job_flow`

## 2. deployment naming 계약

deployment 이름은 [infra/ops/branch_deployments.py](/home/esillileu/discoverex/engine/infra/ops/branch_deployments.py) 에서 정규화한다.

기본 naming:

- `discoverex-generate-<purpose>`
- `discoverex-verify-<purpose>`
- `discoverex-animate-<purpose>`
- `discoverex-combined-<purpose>`

지원 purpose:

- `standard`
- `batch`
- `debug`
- `backfill`

기본 queue mapping:

- `standard` -> `gpu-fixed`
- `batch` -> `gpu-fixed-batch`
- `debug` -> `gpu-fixed-debug`
- `backfill` -> `gpu-fixed-backfill`

## 3. 등록된 flow 파라미터

등록 flow는 다음 파라미터를 받는다.

- `job_spec_json`
- optional `resume_key`
- optional `checkpoint_dir`

실제 시그니처는 [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)에 정의되어 있다.

## 4. 실행 모델 계약

등록 이후 실행 모델은 다음 경계를 갖는다.

1. submitter가 `job_spec_json` 을 deployment에 전달한다.
2. Prefect가 worker pool 과 queue에 flow run을 배치한다.
3. worker/runtime 레이어가 env 와 runtime settings를 준비한다.
4. 엔진이 extracted inputs payload로 실행된다.
5. worker-owned artifact가 기록된다.
6. engine-owned artifact는 manifest 계약을 통해 후처리될 수 있다.

세부 env 와 artifact 책임은 하위 계약 문서를 따른다.

## 5. sweep 계약 경계

이 문서는 sweep 운영 절차를 설명하지 않는다. 다만 등록/실행 경계상 다음 사실은 안정 계약으로 본다.

- sweep 입력은 `--sweep-spec <yaml>` 기반이다
- repo-managed submitted manifest 기본 위치는 `infra/ops/manifests/<sweep-id>.submitted.json` 이다
- sweep spec 은 `infra/ops/specs/sweep/` 아래에 존재한다

운영 규칙과 상태 분류는 [docs/ops/sweeps.md](/home/esillileu/discoverex/engine/docs/ops/sweeps.md)를 본다.

## 6. source/import 요구사항

runtime은 최소한 다음 모듈을 import 가능해야 한다.

- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)

embedded worker stack의 mount 전제는 [infra/worker/README.md](/home/esillileu/discoverex/engine/infra/worker/README.md)에 둔다.

## 7. stable boundary

외부 소비자 기준 안정 경계는 다음이다.

- `prefect_flow.py` 의 공개 callable 사용
- 유효한 `job_spec_json` 제공
- worker-managed runtime env 와 artifact handling 신뢰

내부 handler 이름, lazy import, stage task 분해 방식은 안정 계약에 포함하지 않는다.
