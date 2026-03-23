# Discoverex Core Engine

Discoverex Core Engine is the execution repository for hidden-object scene generation and validation. It contains the engine runtime, Prefect flow entrypoints, worker tooling, and registration scripts needed to run the pipeline locally or through a worker pool.

## What This Project Does

- Generates hidden-object scenes from a background asset or background prompt.
- Verifies generated scenes with logical and perception checks.
- Exposes a validator pipeline for checking a composite image plus object layers.
- Runs the same engine through local CLI execution or Prefect-managed worker execution.
- Persists run metadata through MLflow and worker-managed artifact contracts.

## Main Runtime Surfaces

### Engine CLI

The package exposes `discoverex` as the main Typer CLI.

- `generate`: scene generation pipeline
- `verify`: verification pipeline for an existing `scene.json`
- `animate`: animation entrypoint, currently backed by replay/stub handlers
- `validate`: validator pipeline for a composite image and object layers
- `e2e`: local runtime contract harness

### Prefect Entry Points

The repository root exposes Prefect callables through [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py).

- `run_job_flow`
- `run_generate_job_flow`
- `run_verify_job_flow`
- `run_animate_job_flow`
- `run_combined_job_flow`

These are backed by [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py) and registered under:

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

### Project CLI

`./bin/cli` is the operations wrapper for registration and worker lifecycle tasks.

- `./bin/cli prefect run gen|obj`: standard Prefect job submission
- `./bin/cli prefect sweep run|collect`: object-quality sweep submission and collection
- `./bin/cli prefect deploy|register ...`: lower-level Prefect deployment and submission helpers
- `./bin/cli worker fixed ...`: embedded fixed worker lifecycle
- `./bin/cli artifacts ...`: artifact helpers
- `./bin/cli legacy ...`: legacy helper commands

## Stack

### Language and packaging

- Python 3.11+
- `uv` for environment sync and execution
- Hatchling for packaging

### Core application libraries

- Typer for CLI entrypoints
- Prefect 3 for orchestration
- Hydra for config composition
- Pydantic and pydantic-settings for typed config and contracts
- PyYAML for YAML job spec handling

### Tracking, storage, and model extras

- MLflow for tracking
- boto3 and SQLAlchemy storage extras
- PyTorch, Diffusers, Transformers, Kornia, Real-ESRGAN and related GPU/ML extras
- Ultralytics and MobileSAM in validator-related extras

## Repository Layout

- [src/discoverex](/home/esillileu/discoverex/engine/src/discoverex): engine application, domain, adapters, flows, contracts
- [conf](/home/esillileu/discoverex/engine/conf): Hydra configs and profiles
- [infra/prefect](/home/esillileu/discoverex/engine/infra/prefect): Prefect runtime and flow logic
- [infra/ops](/home/esillileu/discoverex/engine/infra/ops): deployment and job registration scripts
- [infra/worker](/home/esillileu/discoverex/engine/infra/worker): embedded worker stack
- [scripts/cli](/home/esillileu/discoverex/engine/scripts/cli): project operations CLI implementation
- [tests](/home/esillileu/discoverex/engine/tests): unit, contract, runtime, and E2E-oriented tests

## Quick Start

```bash
just init
just run discoverex generate --background-asset-ref bg://dummy
```

For CPU-oriented local runs:

```bash
just run discoverex generate --background-asset-ref bg://dummy -o profile=cpu_fast
```

## Validation Commands

```bash
just lint
just typecheck
just test
```

## Documentation Map

- [Architecture](/home/esillileu/discoverex/engine/.context/architecture.md)
- [Capabilities](/home/esillileu/discoverex/engine/.context/capabilities.md)
- [CLI Guide](/home/esillileu/discoverex/engine/docs/ops/cli.md)
- [Object Quality Sweeps](/home/esillileu/discoverex/engine/docs/ops/object-quality-sweeps.md)
- [Runtime Guide](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- [Engine Run Contract](/home/esillileu/discoverex/engine/docs/contracts/engine-run.md)
- [Orchestrator Contract](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md)
- [Registration Contract](/home/esillileu/discoverex/engine/docs/contracts/registration/README.md)
- [Developer Handoff](/home/esillileu/discoverex/engine/docs/dev/handoff.md)
