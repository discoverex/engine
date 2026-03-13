# Engine Artifact Persistence Contract

This document defines what is persisted automatically today, what is not, and
what an external engine repository must do to remain compatible.

## 1) Persisted automatically by the worker

The worker always persists these orchestration artifacts:

- `stdout.log`
- `stderr.log`
- `result.json`
- `artifacts.json`

Current object layout:

- `jobs/{flow_run_id}/attempt-{attempt}/stdout.log`
- `jobs/{flow_run_id}/attempt-{attempt}/stderr.log`
- `jobs/{flow_run_id}/attempt-{attempt}/result.json`
- `jobs/{flow_run_id}/attempt-{attempt}/artifacts.json`

Current implementation:

- [src/flows/engine_run/task/uploads.py](/home/esillileu/discoverex/orchestrator/src/flows/engine_run/task/uploads.py)

## 2) What `result.json` is for

`result.json` is the worker-owned machine-readable run result. At minimum it
contains:

- `exit_code`
- `resolved_commit`
- `run_mode`
- `entrypoint`

The engine may also emit structured JSON to `stdout`, but the canonical worker
artifact remains `result.json`.

## 3) What is not persisted automatically today

The current worker contract does not automatically upload arbitrary engine
output files such as:

- model checkpoints
- scene bundles
- generated datasets
- intermediate reports
- binary result files
- large final outputs beyond `result.json`

If the engine writes such files into the local workdir, they are not currently
durable unless an explicit engine-artifact upload path is added.

## 4) Compatibility requirement today

A fully worker-compatible engine must assume only this durable baseline:

- logs are durable through worker upload
- `result.json` is durable through worker upload
- MLflow metadata is durable through MLflow

The engine must not assume that arbitrary local files become durable
automatically.

## 5) Official contract for durable engine artifacts

The official contract going forward is worker-managed artifact directory upload.

Normative spec:

- [worker-managed-output-directory-contract.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/worker-managed-output-directory-contract.md)

Under that contract:

1. engine writes durable output files under a worker-provided directory
2. engine writes a manifest describing those files
3. worker validates the manifest
4. worker requests presigned URLs from storage-api
5. worker uploads the files
6. worker records resulting `object_uri` values
7. worker mirrors selected URIs into MLflow tags

## 6) Why direct engine presign support is not required

Direct presign support in the engine is not required for baseline compatibility.

It should remain optional because:

- it pushes storage auth details into the engine runtime
- it increases engine/orchestrator coupling
- worker-managed upload keeps the trust boundary cleaner

Direct presign support becomes necessary only if the engine must upload files
during execution and the worker cannot perform a post-run upload step. That is
not the primary contract for this system.

## 7) Recommended MLflow linkage for stored artifacts

When durable artifact uploads exist, these MLflow tag patterns are recommended:

- `artifact_manifest_uri`
- `artifact_stdout_uri`
- `artifact_stderr_uri`
- `artifact_result_uri`

If engine-owned durable artifacts are added, extend this pattern with stable
tag names such as:

- `artifact_bundle_uri`
- `artifact_checkpoint_uri`
- `artifact_report_uri`

Reference tagging example:

- [scripts/e2e/shell_python_helpers.py](/home/esillileu/discoverex/orchestrator/scripts/e2e/shell_python_helpers.py)

## 8) Decision point

If the target integration requires only:

- execution logs
- final status
- lightweight structured result metadata
- MLflow params/metrics/tags

then the current contract is sufficient.

If the target integration also requires durable intermediate or final files in
MinIO, the worker-managed output-directory contract above must be implemented.
