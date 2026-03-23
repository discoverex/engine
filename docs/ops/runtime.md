# Discoverex Runtime Guide

This document describes how the engine runs locally and under Prefect-managed workers.

## 1. Execution Modes

### Local mode

Local mode is used for development and direct CLI execution.

- entrypoint: `uv run discoverex ...`
- runtime mode in inline job specs: `local`
- typical storage: local files under `artifacts/`
- typical tracking: local MLflow or explicitly configured tracking URI

### Worker mode

Worker mode is used when the engine is launched from a Prefect flow.

- entrypoint: Prefect callable in [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- runtime env is prepared by [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)
- worker-managed artifacts and MLflow linkage are applied after engine execution

## 2. Public Engine Commands

The engine runtime supports:

- `generate`
- `verify`
- `animate`
- `validate`

Compatibility commands are still present for migration support:

- `gen-verify`
- `verify-only`
- `replay-eval`

Only `generate`, `verify`, and `animate` participate in the Prefect job-flow contract. `validate` is a direct CLI pipeline.

## 3. Prefect Flow Surface

External flow entrypoints:

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

Internal engine flows:

- `discoverex-engine-entry-pipeline`
- `discoverex-generate-pipeline`
- `discoverex-verify-pipeline`
- `discoverex-generate-inpaint-variant-pack`

`discoverex-combined-flow` explicitly decomposes `gen-verify` into sequential `generate` then `verify`.

## 4. Worker-Provided Runtime Contract

During Prefect execution, the worker/runtime layer provides environment values including:

- `ORCH_JOB_INPUTS_JSON`
- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `MLFLOW_TRACKING_URI`

The engine should:

- use `MLFLOW_TRACKING_URI` as provided
- write durable engine-owned files only under `ORCH_ENGINE_ARTIFACT_DIR`
- write the manifest to `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH` when durable artifacts exist

## 5. Local Execution Examples

### Basic generate

```bash
just run discoverex generate --background-asset-ref bg://dummy
```

### CPU-oriented generate profile

```bash
just run discoverex generate --background-asset-ref bg://dummy -o profile=cpu_fast
```

### Verify an existing scene

```bash
just run discoverex verify --scene-json artifacts/.../scene.json
```

### Validator run

```bash
just run discoverex validate composite.png --object-layer obj1.png --object-layer obj2.png
```

## 6. Worker Debug Example

The contract can be simulated locally by injecting worker env values:

```bash
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
ORCH_ENGINE_ARTIFACT_DIR="$PWD/.tmp/engine-artifacts" \
ORCH_ENGINE_ARTIFACT_MANIFEST_PATH="$PWD/.tmp/engine-artifacts.json" \
uv run discoverex generate \
  --background-asset-ref bg://dummy \
  -o adapters/tracker=mlflow_server
```

## 7. Embedded Fixed Worker

The repository includes an embedded worker stack documented in [infra/worker/README.md](/home/esillileu/discoverex/engine/infra/worker/README.md).

Common commands:

```bash
./bin/cli worker init
./bin/cli worker fixed up
./bin/cli worker fixed logs --tail 120 -f
./bin/cli worker fixed doctor --json
```

## 8. Validation and Smoke Checks

```bash
just lint
just typecheck
just test
uv run discoverex e2e --scenario all
```

The `e2e` harness covers:

- `tracking-artifact`
- `worker-contract`
- `live-services`

## 9. Current Operational Notes

- `generate` and `verify` are the most complete paths.
- `animate` is still wired through compatibility/stub-oriented handlers.
- Worker registration and execution assume branch-scoped Prefect deployments managed from `infra/register`.
