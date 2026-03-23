# Worker-Managed Output Directory Contract

This is the canonical contract for durable engine-owned artifacts.

## 1. Worker-Provided Paths

The worker provides:

- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`

`ORCH_ENGINE_ARTIFACT_DIR` is the only allowed durable output root for engine-owned files.

## 2. Engine Write Rules

The engine must:

- write durable files only under `ORCH_ENGINE_ARTIFACT_DIR`
- use relative paths in the manifest
- avoid absolute paths
- avoid `..` path traversal
- finish writing files before exit

## 3. Manifest Shape

The manifest must contain:

- `schema_version`
- `artifacts`

Each artifact entry must contain:

- `logical_name`
- `relative_path`

Optional fields may include:

- `content_type`
- `mlflow_tag`
- `description`

## 4. Worker Upload Rules

After engine execution, the worker:

1. reads the manifest
2. validates that every path stays under the artifact root
3. uploads declared files
4. records uploaded object URIs
5. mirrors selected URIs into MLflow tags when configured

## 5. Remote Layout

Engine-owned durable artifacts are uploaded under:

- `jobs/{flow_run_id}/attempt-{attempt}/engine/`

The worker also writes an engine-artifact manifest object:

- `jobs/{flow_run_id}/attempt-{attempt}/engine-artifacts.json`

## 6. Empty Artifact Case

If the engine has no additional durable artifacts:

- the directory may remain empty
- the manifest may be omitted

That should not be treated as an error.
