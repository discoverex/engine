# Runtime Auth And Environment

This document defines the runtime environment that the Prefect/worker layer provides to the engine and the boundaries the engine should respect.

## 1. Worker-Provided Environment

Common engine-facing values include:

- `ORCH_JOB_INPUTS_JSON`
- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `MLFLOW_TRACKING_URI`

The runtime layer also derives flow-run metadata such as flow run id, attempt, outputs prefix, and resolved settings.

## 2. Auth Boundary

The engine should not depend directly on:

- Prefect API auth headers
- object-store credentials
- storage presign routes
- backend MLflow container topology

Those concerns are owned by the worker/runtime/ops layer.

## 3. MLflow Behavior

The engine should use `MLFLOW_TRACKING_URI` exactly as provided.

If access mediation or proxying is required, it should happen before the engine sees the URI. The engine should not require Cloudflare Access headers or internal backend addresses.

## 4. Artifact Boundary

If durable engine-owned artifacts are produced:

- write files only under `ORCH_ENGINE_ARTIFACT_DIR`
- write the manifest to `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`

The worker remains responsible for upload and object URI recording.

## 5. Host Expectations

Worker environments are expected to provide:

- reachable Prefect API configuration
- any storage or MLflow connectivity needed by the worker
- writable runtime directories
- GPU runtime prerequisites when GPU paths are used

The engine contract assumes those prerequisites already exist.
