# Runtime Auth And Environment

This document defines what the worker provides to the engine process and what
the engine must not depend on directly.

## 1) Worker-injected runtime environment

Before launching the engine process, the worker injects:

- `ORCH_ENGINE`
- `ORCH_RUN_MODE`
- `ORCH_FLOW_RUN_ID`
- `ORCH_ATTEMPT`
- `ORCH_OUTPUTS_PREFIX`
- `ORCH_RESOLVED_COMMIT`
- `ORCH_JOB_INPUTS_JSON`
- `ORCH_ENGINE_ARTIFACT_DIR` under the worker-managed output-directory contract
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH` under the worker-managed output-directory contract

Conditionally injected:

- `ORCH_JOB_NAME`
- `ORCH_JOB_CONFIG_PATH`

Additionally, values from `job_spec.env` are merged into the child process
environment.

Reference implementation:

- [src/runner/entrypoint/core.py](/home/esillileu/discoverex/orchestrator/src/runner/entrypoint/core.py)

## 2) Repository execution model

For `run_mode=repo`, the worker:

1. resolves `ref` to a concrete commit
2. prepares a temporary workdir
3. clones and checks out the target repository
4. optionally prepares a per-repo Python environment
5. executes the configured `entrypoint`

Current dependency behavior:

- if `pyproject.toml` exists, worker may run `uv sync`
- if `uv.lock` exists, worker may run `uv sync --frozen`

The engine repo should therefore be runnable with deterministic repo-local
dependencies.

## 3) Authentication boundary

The engine should not need to know or manage authentication for:

- Prefect API
- storage-api presign routes
- MinIO object-store credentials
- MLflow backend container addresses
- MLflow database credentials

Those concerns stay with orchestrator operations, workers, and storage-node
services.

## 4) Prefect auth expectations

Normal engine execution does not require the engine process to call Prefect.

Prefect auth is managed by:

- register stack
- workers
- submit routers
- observability tools

If Prefect is protected by Cloudflare Access, those clients send:

- `CF-Access-Client-Id`
- `CF-Access-Client-Secret`

The engine should not require these headers as runtime inputs.

## 5) Storage auth expectations

The worker is responsible for all orchestration artifact storage calls.

Worker-managed inputs include:

- `STORAGE_API_URL`
- Cloudflare Access credentials for storage-api
- presign request/response handling
- signed upload URL usage

The engine must not require:

- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- direct access to internal storage endpoints

Durable engine-owned artifacts are expected to flow through the worker-managed
output-directory contract, not through direct engine-side object-store auth.

## 6) MLflow auth and proxy behavior

The engine may write MLflow metadata only through the worker-facing tracking
URI:

- `MLFLOW_TRACKING_URI`

When the tracking URI is remote HTTP(S) and protected by Cloudflare Access, the
worker may:

1. start a local HTTP proxy
2. inject Access headers on outbound MLflow requests
3. rewrite `MLFLOW_TRACKING_URI` for the engine process
4. remove direct CF credentials from the engine child environment

The engine should therefore:

- use `MLFLOW_TRACKING_URI` exactly as provided
- not depend on direct Cloudflare Access headers
- not depend on backend MLflow hostnames

Reference implementation:

- [src/runner/mlflow_proxy.py](/home/esillileu/discoverex/orchestrator/src/runner/mlflow_proxy.py)

## 7) Host and worker prerequisites

The worker environment is expected to provide:

- reachable `PREFECT_API_URL`
- reachable `STORAGE_API_URL`
- working DNS for public service hosts
- writable checkpoint storage

For GPU engines, the worker host must also already provide:

- GPU runtime
- drivers
- framework-compatible image/runtime stack

The orchestrator does not install host-level packages during a run.
