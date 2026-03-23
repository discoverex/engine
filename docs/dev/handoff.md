# Developer Handoff

This document summarizes the current repository state for the next engineer.

## 1. Repository Reality

This is an active engine repository, not a docs-only migration workspace.

It contains:

- the `discoverex` runtime package
- Prefect flow entrypoints
- registration scripts
- an embedded worker stack
- contract, runtime, and model tests

## 2. Most Important Surfaces

- engine CLI: [src/discoverex/adapters/inbound/cli/main.py](/home/esillileu/discoverex/engine/src/discoverex/adapters/inbound/cli/main.py)
- Prefect runtime: [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)
- public flow exports: [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- registration scripts: [infra/register](/home/esillileu/discoverex/engine/infra/register)
- ops CLI: [scripts/cli](/home/esillileu/discoverex/engine/scripts/cli)

## 3. Current Functional Shape

- `generate` and `verify` are the strongest runtime paths.
- `validate` exists as a direct CLI validator pipeline.
- `animate` remains public but still relies on compatibility/stub-oriented handlers.
- worker-managed artifact persistence is part of the current runtime model.

## 4. Recommended First Checks

```bash
just test
just run discoverex generate --background-asset-ref bg://dummy
./bin/cli prefect deploy flow generate --branch "$(git branch --show-current)"
```

## 5. Open Attention Areas

- keep `animate` expectations conservative until the runtime path is fully implemented
- verify worker/deployment assumptions after changes to `infra/prefect`, `infra/register`, or `infra/worker`
- keep docs aligned with actual CLI and flow names
