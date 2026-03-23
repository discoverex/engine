# Orchestrator And Worker Contract

This document defines the external contract used when the engine is executed through Prefect-managed flows and workers.

## 1. Public Prefect Entry Points

Repository-root callable surface:

- `prefect_flow.py:run_job_flow`
- `prefect_flow.py:run_generate_job_flow`
- `prefect_flow.py:run_verify_job_flow`
- `prefect_flow.py:run_animate_job_flow`
- `prefect_flow.py:run_combined_job_flow`

Registered flow names:

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

## 2. Flow Roles

- `discoverex-engine-flow`: generic job-spec entrypoint
- `discoverex-generate-flow`: command-constrained generate entrypoint
- `discoverex-verify-flow`: command-constrained verify entrypoint
- `discoverex-animate-flow`: command-constrained animate entrypoint
- `discoverex-combined-flow`: explicit composite execution path, especially `gen-verify`

`discoverex-combined-flow` can decompose `gen-verify` into sequential `generate` then `verify`.

## 3. Job Spec Shape

The Prefect layer receives `job_spec_json` and extracts an engine payload from it.

Important top-level fields include:

- `engine`
- `repo_url`
- `ref`
- `entrypoint`
- `inputs`
- `env`

The engine-facing portion is carried in `inputs`.

## 4. Worker Runtime Environment

The runtime layer provides environment values including:

- `ORCH_JOB_INPUTS_JSON`
- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `MLFLOW_TRACKING_URI`

The worker/runtime layer also computes flow-run metadata such as:

- flow run id
- attempt number
- outputs prefix
- resolved settings snapshot

## 5. Artifact Responsibilities

The worker always persists worker-owned orchestration artifacts:

- `stdout.log`
- `stderr.log`
- `result.json`
- `artifacts.json`

If the engine writes durable engine-owned artifacts:

- files must be written under `ORCH_ENGINE_ARTIFACT_DIR`
- manifest must be written to `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- upload is performed by the worker after execution

## 6. MLflow Boundary

The engine may write run metadata through `MLFLOW_TRACKING_URI`.

The worker remains responsible for:

- artifact upload
- uploaded object URI recording
- MLflow artifact-link tagging after upload

The engine should not depend on:

- direct MinIO credentials
- presign routes
- backend MLflow host assumptions

## 7. Command Compatibility

Public Prefect-facing commands:

- `generate`
- `verify`
- `animate`

Compatibility aliases:

- `gen-verify`
- `verify-only`
- `replay-eval`

Current mapping:

- `gen-verify` -> `generate` or explicit combined decomposition
- `verify-only` -> `verify`
- `replay-eval` -> `animate`

## 8. Current Operational Reality

- `generate` and `verify` are the most complete contract paths.
- `animate` is wired into the runtime surface but still depends on compatibility/stub-oriented internal handlers.
- Deployment creation and job submission are managed by scripts under [infra/ops](/home/esillileu/discoverex/engine/infra/ops).
