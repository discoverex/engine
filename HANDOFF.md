# Handoff

## Current State

- Repository type: active engine runtime and orchestration repo
- Main runtime: `discoverex` CLI plus Prefect flow entrypoints
- Core operational areas: `src/discoverex`, `infra/prefect`, `infra/register`, `infra/worker`, `scripts/cli`

## Current Public Runtime Surface

- CLI commands: `generate`, `verify`, `animate`, `validate`, `e2e`
- Prefect flows: `discoverex-engine-flow`, `discoverex-generate-flow`, `discoverex-verify-flow`, `discoverex-animate-flow`, `discoverex-combined-flow`
- Project ops CLI: `./bin/cli prefect ...`, `./bin/cli worker fixed ...`

## Practical Notes

- `generate` and `verify` are the most complete execution paths.
- `animate` is exposed but still backed by compatibility/stub-oriented internals.
- Worker-managed artifact upload and MLflow linkage are part of the current contract.

## Files To Read First

- [README.md](/home/esillileu/discoverex/engine/README.md)
- [docs/ops/runtime.md](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- [docs/contracts/orchestrator.md](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md)
- [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)
- [src/discoverex/adapters/inbound/cli/main.py](/home/esillileu/discoverex/engine/src/discoverex/adapters/inbound/cli/main.py)
