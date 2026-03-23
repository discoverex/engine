# Discoverex CLI Guide

This repository has two CLI surfaces:

- `discoverex`: the engine runtime CLI exposed by the Python package
- `./bin/cli`: the project operations wrapper for Prefect, worker, and artifact tasks

## 1. Engine CLI: `discoverex`

Main implementation: [src/discoverex/adapters/inbound/cli/main.py](/home/esillileu/discoverex/engine/src/discoverex/adapters/inbound/cli/main.py)

### `generate`

Runs the generation pipeline.

```bash
uv run discoverex generate --background-asset-ref bg://dummy
uv run discoverex generate --background-prompt "kitchen interior" --object-prompt "red mug"
```

Important options:

- `--background-asset-ref`
- `--background-prompt`
- `--object-prompt`
- `--final-prompt`
- `--config-name`
- `--config-dir`
- `-o`, `--override`
- `--verbose`

At least one of `--background-asset-ref` or `--background-prompt` is required.

### `verify`

Runs verification for an existing scene document.

```bash
uv run discoverex verify --scene-json artifacts/.../scene.json
```

### `animate`

Runs the animation entrypoint.

```bash
uv run discoverex animate --scene-jsons artifacts/.../scene.json
```

The public command exists and is wired into Prefect, but current behavior still depends on replay/stub handlers rather than a completed production animation pipeline.

### `validate`

Runs the validator pipeline on a composite image and one or more object-layer PNGs.

```bash
uv run discoverex validate composite.png --object-layer obj1.png --object-layer obj2.png
```

### `e2e`

Runs the local runtime-contract harness.

```bash
uv run discoverex e2e --scenario all
uv run discoverex e2e --scenario live-services --ensure-live-infra
```

Supported scenarios:

- `tracking-artifact`
- `worker-contract`
- `live-services`
- `all`

### Legacy hidden commands

The CLI still carries hidden compatibility commands:

- `gen-verify`
- `verify-only`
- `replay-eval`

They emit deprecation warnings and map to `generate`, `verify`, and `animate`.

## 2. Project CLI: `./bin/cli`

Main implementation: [scripts/cli/main.py](/home/esillileu/discoverex/engine/scripts/cli/main.py)

Subcommands:

- `prefect`
- `worker`
- `artifacts`
- `legacy`

## 3. `./bin/cli prefect`

Implementation: [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)

### Deploy flow

Registers a branch-scoped Prefect deployment.

```bash
./bin/cli prefect deploy flow generate --branch dev --work-pool-name gpu-pool
./bin/cli prefect deploy flow combined --branch dev
```

### Register flow

Submits a standard job spec to a deployment.

```bash
./bin/cli prefect register flow generate --branch dev
./bin/cli prefect register flow combined --branch dev
```

### Register batch

Fans out jobs from a CSV file.

```bash
./bin/cli prefect register batch scenes.csv --branch dev
```

### Experiment deployment and sweep

```bash
./bin/cli prefect deploy experiment --experiment naturalness --branch dev
./bin/cli prefect register experiment-sweep --experiment naturalness --branch dev
```

### Build or submit a raw spec

```bash
./bin/cli prefect build-spec ...
./bin/cli prefect submit-spec path/to/job.yaml
```

### Inspect logs and run tree

```bash
./bin/cli prefect check-logs <FLOW_RUN_ID>
./bin/cli prefect inspect-run <FLOW_RUN_ID>
```

## 4. `./bin/cli worker fixed`

Implementation: [scripts/cli/worker.py](/home/esillileu/discoverex/engine/scripts/cli/worker.py)

Commands:

- `./bin/cli worker init`
- `./bin/cli worker fixed up`
- `./bin/cli worker fixed down`
- `./bin/cli worker fixed ps`
- `./bin/cli worker fixed logs --tail 120 -f`
- `./bin/cli worker fixed build`
- `./bin/cli worker fixed doctor`

This surface operates the embedded Docker-based fixed worker stack defined under [infra/worker](/home/esillileu/discoverex/engine/infra/worker).

## 5. Recommended Day-to-Day Commands

```bash
just init
just run discoverex generate --background-asset-ref bg://dummy
just test
./bin/cli prefect deploy flow generate --branch "$(git branch --show-current)"
```
