# Execution Contract (Prefect)

This document defines the wrapper-facing `JobSpec` used by Prefect and workers.
The engine itself executes the nested `inputs` payload, which is the canonical
engine-facing runtime contract.

## Flow Input

- `job_spec_json: str`
- `resume_key: str | None` (optional)
- `checkpoint_dir: str | None` (optional)

Official registration entrypoint:

- `prefect_flow.py:run_job_flow`
- Prefect flow name: `disoverex-engine-flow`

Responsibility boundary:

- Engine repo owns the registerable flow callable and runtime compatibility.
- External operator/orchestrator owns deployment creation, refresh, and later submission.
- `infra/register/*` scripts in this repo are compatibility/helper tooling, not the public operator contract.

`job_spec_json` schema:

- `engine: str`
- `repo_url: str`
- `ref: str` (branch/tag/sha)
- `entrypoint: list[str]`
- `config: str | None` (repo-relative path only)
- `job_name: str | None`
- `inputs: dict[str, Any]`
- `env: dict[str, str]`
- `outputs_prefix: str | None`

Runtime environment expected from the worker:

- `ORCH_JOB_INPUTS_JSON`
- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `MLFLOW_TRACKING_URI`

`inputs` schema:

- `contract_version: "v1" | "v2"`
- `command: str`
- `config_name: str | None`
- `config_dir: str | None`
- `args: dict[str, Any]`
- `overrides: list[str]`
- `runtime: { mode, bootstrap_mode, extras, extra_env }`

## Version Pinning Policy

- Flow starts with `resolve_commit(ref)`.
- If `ref` is branch/tag, it is resolved once to `resolved_commit`.
- All retries use the same `resolved_commit`.

## Artifact Layout

- `jobs/{flow_run_id}/attempt-{attempt}/stdout.log`
- `jobs/{flow_run_id}/attempt-{attempt}/stderr.log`
- `jobs/{flow_run_id}/attempt-{attempt}/result.json`
- `jobs/{flow_run_id}/attempt-{attempt}/artifacts.json`

## Storage Gateway APIs

- `POST /v1/presign/put`
- `POST /v1/presign/get`
- `POST /v1/presign/batch`
- `POST /v1/object/head`
- `PUT /v1/object/proxy?token=...`
- `GET /v1/object/proxy?token=...`

All endpoints require bearer auth:

- `CF-Access-Client-Id: <cf_access_client_id>`
- `CF-Access-Client-Secret: <cf_access_client_secret>`

Optional additional gateway protection:

- Cloudflare Access service-token headers:
  - `CF-Access-Client-Id`
  - `CF-Access-Client-Secret`

## Flow Result Metadata

- `flow_run_id`
- `attempt`
- `resolved_commit`
- `outputs_prefix`
- `stdout_uri`
- `stderr_uri`
- `result_uri`
- `manifest_uri`
- `exit_code`

`Prefect flow result` is the source of truth for run metadata.

Implementation-facing runtime contract:

- [Engine Run Contract](/home/esillileu/discoverex/engine/docs/engine-run-contract.md)
- [Engine Implementation Contract](/home/esillileu/discoverex/orchestrator/docs/dev/engine-implementation-contract.md)

## E2E Acceptance (Register -> Worker -> Storage)

The deterministic script `scripts/e2e/e2e_local_orchestrator.sh` verifies the orchestration chain in two modes:

- `core`: deployment register, worker execution, object persistence in MinIO
- `mlflow`: `core` + MLflow run tag linkage (`artifact_*_uri`)

Core pass criteria:

1. `disoverex-engine-flow/discoverex-engine-job` deployment exists after register.
2. Submitted flow run reaches `COMPLETED`.
3. All required objects exist:
   - `stdout.log`
   - `stderr.log`
   - `result.json`
   - `artifacts.json`
4. `artifacts.json` metadata matches expected `flow_run_id`, `attempt`, and object URIs.
