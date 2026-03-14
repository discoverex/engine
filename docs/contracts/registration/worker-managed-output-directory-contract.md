# Worker-Managed Output Directory Contract

Status:

- official contract for external engine integration
- worker implementation may still need to catch up where noted

This document defines the concrete contract for durable engine-owned artifacts.
The engine writes files into a worker-provided local directory, and the worker
is responsible for uploading them to storage.

## 1) Contract goals

This contract exists to keep:

- MinIO credentials out of the engine
- presign logic out of the engine
- storage naming/layout controlled by the orchestrator
- durable engine artifacts available in storage and MLflow

## 2) Worker-provided paths

The worker must provide these environment variables to the engine process:

- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`

Semantics:

- `ORCH_ENGINE_ARTIFACT_DIR` is a writable local directory created by the worker
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH` is the JSON manifest file path the engine
  writes before exiting successfully

The engine must treat both paths as ephemeral local paths owned by the worker
runtime.

## 3) Engine write contract

The engine may write any durable output files only under:

- `ORCH_ENGINE_ARTIFACT_DIR`

Rules:

- every persisted artifact path must stay under `ORCH_ENGINE_ARTIFACT_DIR`
- paths in the manifest must be relative paths, not absolute paths
- relative paths must not contain `..`
- the engine must finish writing files before process exit
- the engine must write a single manifest JSON file to
  `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`

The engine must not assume that files written outside
`ORCH_ENGINE_ARTIFACT_DIR` become durable.

## 4) Manifest format

Reference example:

- [engine-artifacts.manifest.example.json](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/engine-artifacts.manifest.example.json)

Required top-level fields:

- `schema_version`
- `artifacts`

Required per-artifact fields:

- `logical_name`
- `relative_path`

Optional per-artifact fields:

- `content_type`
- `mlflow_tag`
- `description`

Rules:

- `schema_version` must currently be `1`
- `artifacts` must be a non-empty list if durable engine artifacts were produced
- `relative_path` is relative to `ORCH_ENGINE_ARTIFACT_DIR`
- `mlflow_tag`, if present, is the preferred MLflow tag key for the uploaded
  `object_uri`

## 5) Worker upload contract

After the engine exits, the worker must:

1. read `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
2. validate manifest shape
3. validate that every `relative_path` stays under `ORCH_ENGINE_ARTIFACT_DIR`
4. request presigned upload URLs from storage-api
5. upload the referenced files
6. record returned `object_uri` values in the orchestration manifest
7. expose relevant `object_uri` values in MLflow tags when configured

## 6) Remote object layout

The remote durable object prefix for engine-owned artifacts is:

- `jobs/{flow_run_id}/attempt-{attempt}/engine/`

Each declared artifact is uploaded to:

- `jobs/{flow_run_id}/attempt-{attempt}/engine/{relative_path}`

The worker also writes an engine-artifact manifest object at:

- `jobs/{flow_run_id}/attempt-{attempt}/engine-artifacts.json`

This is separate from the existing worker artifact manifest `artifacts.json`.

## 7) MLflow linkage contract

If MLflow is enabled for the engine run:

- the worker should set one MLflow tag per uploaded engine artifact when
  `mlflow_tag` is provided
- the worker should set `artifact_engine_manifest_uri` to the uploaded engine
  manifest object URI

Recommended stable MLflow tag examples:

- `artifact_scene_uri`
- `artifact_verification_uri`
- `artifact_bundle_uri`
- `artifact_checkpoint_uri`
- `artifact_report_uri`

## 8) Engine behavior on empty artifacts

If the engine has no durable engine-owned artifacts beyond worker-managed logs
and `result.json`, it may:

- leave `ORCH_ENGINE_ARTIFACT_DIR` empty
- omit writing the manifest file

The worker should treat that as:

- no extra engine artifacts to upload
- not an error

## 9) Engine behavior on failure

If the engine process fails:

- worker-managed logs and `result.json` must still be preserved
- any partially written engine artifact directory may be ignored unless the
  worker later adopts best-effort failure artifact upload

For now, the minimum contract guarantees durable engine-owned artifacts only
for runs that complete their artifact manifest write successfully.

## 10) Minimum engine implementation recipe

An engine implementation compatible with this contract should:

1. read `ORCH_ENGINE_ARTIFACT_DIR`
2. write durable files under that directory
3. write `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
4. write MLflow metadata using only `MLFLOW_TRACKING_URI`
5. exit normally and let the worker handle storage upload
