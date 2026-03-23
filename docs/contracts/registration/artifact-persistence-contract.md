# Engine Artifact Persistence Contract

This document describes what is durable by default and how engine-owned artifacts become durable.

## 1. Worker-Owned Durable Artifacts

The worker/runtime layer always persists:

- `stdout.log`
- `stderr.log`
- `result.json`
- `artifacts.json`

These are produced around the execution path in [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py) with upload helpers from the Prefect runtime modules.

## 2. Typical Object Layout

Worker-owned artifacts are organized by flow run and attempt:

- `jobs/{flow_run_id}/attempt-{attempt}/stdout.log`
- `jobs/{flow_run_id}/attempt-{attempt}/stderr.log`
- `jobs/{flow_run_id}/attempt-{attempt}/result.json`
- `jobs/{flow_run_id}/attempt-{attempt}/artifacts.json`

## 3. What Is Not Durable Automatically

Arbitrary files written into a local workdir are not durable by default.

Examples:

- generated bundles
- debug images
- intermediate reports
- custom binary outputs

If the engine needs them to persist, it must use the worker-managed artifact directory contract.

## 4. Official Durable Artifact Path

For engine-owned durable files:

1. write files under `ORCH_ENGINE_ARTIFACT_DIR`
2. write a manifest to `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
3. let the worker upload them after execution

Reference: [worker-managed-output-directory-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/worker-managed-output-directory-contract.md)

## 5. MLflow Linkage

The engine may emit `mlflow_run_id` in its result payload. The worker uses that run id for post-upload URI tagging.

The engine should not:

- guess uploaded object URIs
- upload directly to object storage as part of the default contract
- write worker-owned MLflow artifact-link tags itself
