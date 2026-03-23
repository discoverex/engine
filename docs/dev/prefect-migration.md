# Prefect Migration Status

This document tracks the current Prefect-based execution model in this repository.

## 1. Current Baseline

The repository is already operating on a Prefect-first execution model.

Implemented baseline:

- public Prefect callables exposed from `prefect_flow.py`
- active deployment and registration scripts under `infra/ops`
- worker/runtime execution path under `infra/prefect`
- explicit `discoverex-combined-flow` handling for composite execution
- worker-managed artifact persistence and upload hooks
- `prefect sweep run|collect` as the supported object-quality sweep surface

## 2. Stable Public Surface

Prefect flow names:

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

Public commands used by the flow contract:

- `generate`
- `verify`
- `animate`

Public operations wrapper commands:

- `./bin/cli prefect run gen`
- `./bin/cli prefect run obj`
- `./bin/cli prefect sweep run --sweep-spec <path>`
- `./bin/cli prefect sweep collect --sweep-spec <path>`

Compatibility aliases remain present for migration support.

## 3. What Is Complete

- `generate` and `verify` paths are integrated into the current Prefect runtime.
- Registration and submission tooling exist in-repo.
- Process-pool deployment creation is verified with `Flow.from_source(...)` against the live Prefect server.
- Object-quality sweep submit and collect flows are smoke-tested against the live Prefect server.
- Local and worker contract E2E harnesses exist.
- Runtime artifact and MLflow linkage boundaries are documented in `docs/contracts`.

## 4. Remaining Gaps

- `animate` is still not a fully realized production pipeline.
- Sweep support is SSOT only for the object-quality path in this pass.
- Compatibility aliases still exist and need an eventual removal policy.

## 5. Related Files

- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)
- [infra/ops/deploy_prefect_flows.py](/home/esillileu/discoverex/engine/infra/ops/deploy_prefect_flows.py)
- [docs/contracts/orchestrator.md](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md)
