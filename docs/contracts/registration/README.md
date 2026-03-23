# Registration Contract

This directory documents how this repository exposes Prefect flows for deployment and how workers execute the engine after registration.

The source of truth for the implementation lives in:

- [infra/ops](/home/esillileu/discoverex/engine/infra/ops)
- [infra/prefect](/home/esillileu/discoverex/engine/infra/prefect)
- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)

Companion documents:

- [runtime-auth-and-env.md](/home/esillileu/discoverex/engine/docs/contracts/registration/runtime-auth-and-env.md)
- [artifact-persistence-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/artifact-persistence-contract.md)
- [worker-managed-output-directory-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/worker-managed-output-directory-contract.md)
- [implementation-checklist.md](/home/esillileu/discoverex/engine/docs/contracts/registration/implementation-checklist.md)

## 1. What Gets Registered

This repository registers purpose-scoped Prefect deployments for these flow kinds:

- `combined`
- `generate`
- `verify`
- `animate`

The public callables live at the repository root:

- `prefect_flow.py:run_job_flow`
- `prefect_flow.py:run_generate_job_flow`
- `prefect_flow.py:run_verify_job_flow`
- `prefect_flow.py:run_animate_job_flow`
- `prefect_flow.py:run_combined_job_flow`

## 2. Registration Implementation

Registration and submission logic lives in:

- [infra/ops/deploy_prefect_flows.py](/home/esillileu/discoverex/engine/infra/ops/deploy_prefect_flows.py)
- [infra/ops/register_prefect_job.py](/home/esillileu/discoverex/engine/infra/ops/register_prefect_job.py)
- [infra/ops/register_orchestrator_job.py](/home/esillileu/discoverex/engine/infra/ops/register_orchestrator_job.py)
- [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)

Operational wrapper commands:

- `./bin/cli prefect deploy flow <flow-kind> --purpose <purpose>`
- `./bin/cli prefect register flow <flow-kind> --purpose <purpose>`
- `./bin/cli prefect register batch <csv> --purpose <purpose>`
- `./bin/cli prefect deploy experiment --experiment <name> --purpose <purpose>`
- `./bin/cli prefect run gen`
- `./bin/cli prefect run obj`
- `./bin/cli prefect sweep run --sweep-spec <path>`
- `./bin/cli prefect sweep collect --sweep-spec <path>`

## 3. Deployment Naming

Deployments are purpose-scoped and normalized through [infra/ops/branch_deployments.py](/home/esillileu/discoverex/engine/infra/ops/branch_deployments.py).

Flow-level naming follows the repository flow kinds and deployment purposes:

- `discoverex-generate-<purpose>`
- `discoverex-verify-<purpose>`
- `discoverex-animate-<purpose>`
- `discoverex-combined-<purpose>`

Supported purposes:

- `standard`
- `batch`
- `debug`
- `backfill`

Default queue mapping:

- `standard` -> `gpu-fixed`
- `batch` -> `gpu-fixed-batch`
- `debug` -> `gpu-fixed-debug`
- `backfill` -> `gpu-fixed-backfill`

Experiment deployments may use a separate naming path when they need explicit experiment IDs, but the base operational surface uses the purpose-scoped names above.

## 4. Expected Flow Parameters

Registered flows accept:

- `job_spec_json`
- optional `resume_key`
- optional `checkpoint_dir`

These match the call signatures implemented in [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py).

## 5. Runtime Model

After registration, execution proceeds as:

1. a submitter sends `job_spec_json` to a deployment
2. Prefect schedules the flow run onto a worker pool and queue
   default queue selection is purpose-based, but run submission may override the queue for isolated experiments
3. the worker/runtime layer resolves env and runtime settings
4. the engine is executed with the extracted inputs payload
5. worker-owned artifacts are written and uploaded
6. engine-owned artifacts are optionally uploaded through the manifest contract

## 6. Sweep Contract

Supported sweep input is always a YAML spec passed as `--sweep-spec <path>`.

Current supported sweep SSOT:

- object-quality sweep submission and collection

Sweep state contract:

- repo-managed submitted manifest defaults to `infra/ops/manifests/<sweep-id>.submitted.json`
- `sweep run` merges by `sweep_id`, `policy_id`, `scenario_id`
- collector classifies rows as `completed`, `pending`, `failed`, `cancelled`, `failed_to_collect`, or `not_submitted`
- queue override remains allowed at submit time with `--work-queue-name`

## 7. Source and Import Requirements

The runtime assumes this repository is importable enough to load:

- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)

The embedded worker stack mounts the minimal live source paths documented in [infra/worker/README.md](/home/esillileu/discoverex/engine/infra/worker/README.md).

## 8. Stable Contract Boundary

The stable registration contract for consumers of this repository is:

- use one of the public Prefect callables in `prefect_flow.py`
- provide a valid `job_spec_json`
- rely on worker-managed runtime env and artifact handling

Internal implementation details such as compatibility handler names, lazy imports, or specific stage task layout are intentionally outside the stable registration boundary.
