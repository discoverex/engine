# Registration Contract

This directory documents how this repository exposes Prefect flows for deployment and how workers execute the engine after registration.

The source of truth for the implementation lives in:

- [infra/register](/home/esillileu/discoverex/engine/infra/register)
- [infra/prefect](/home/esillileu/discoverex/engine/infra/prefect)
- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)

Companion documents:

- [runtime-auth-and-env.md](/home/esillileu/discoverex/engine/docs/contracts/registration/runtime-auth-and-env.md)
- [artifact-persistence-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/artifact-persistence-contract.md)
- [worker-managed-output-directory-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/worker-managed-output-directory-contract.md)
- [implementation-checklist.md](/home/esillileu/discoverex/engine/docs/contracts/registration/implementation-checklist.md)

## 1. What Gets Registered

This repository registers branch-scoped Prefect deployments for these flow kinds:

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

- [infra/register/deploy_prefect_flows.py](/home/esillileu/discoverex/engine/infra/register/deploy_prefect_flows.py)
- [infra/register/register_prefect_job.py](/home/esillileu/discoverex/engine/infra/register/register_prefect_job.py)
- [infra/register/register_orchestrator_job.py](/home/esillileu/discoverex/engine/infra/register/register_orchestrator_job.py)
- [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)

Operational wrapper commands:

- `./bin/cli prefect deploy flow <flow-kind> --branch <branch>`
- `./bin/cli prefect register flow <flow-kind> --branch <branch>`
- `./bin/cli prefect register batch <csv> --branch <branch>`
- `./bin/cli prefect deploy experiment --experiment <name> --branch <branch>`
- `./bin/cli prefect register experiment-sweep --experiment <name> --branch <branch>`

## 3. Deployment Naming

Deployments are branch-scoped and normalized through [infra/register/branch_deployments.py](/home/esillileu/discoverex/engine/infra/register/branch_deployments.py).

Flow-level naming follows the repository flow kinds, for example:

- `discoverex-generate-<branch-slug>`
- `discoverex-verify-<branch-slug>`
- `discoverex-animate-<branch-slug>`
- `discoverex-combined-<branch-slug>`

Experiment deployments use a separate naming path.

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
3. the worker/runtime layer resolves env and runtime settings
4. the engine is executed with the extracted inputs payload
5. worker-owned artifacts are written and uploaded
6. engine-owned artifacts are optionally uploaded through the manifest contract

## 6. Source and Import Requirements

The runtime assumes this repository is importable enough to load:

- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)

The embedded worker stack mounts the minimal live source paths documented in [infra/worker/README.md](/home/esillileu/discoverex/engine/infra/worker/README.md).

## 7. Stable Contract Boundary

The stable registration contract for consumers of this repository is:

- use one of the public Prefect callables in `prefect_flow.py`
- provide a valid `job_spec_json`
- rely on worker-managed runtime env and artifact handling

Internal implementation details such as compatibility handler names, lazy imports, or specific stage task layout are intentionally outside the stable registration boundary.
