# Engine Integration Checklist

Use this checklist when building or reviewing an external engine repository for
worker compatibility.

## 1) Flow registration readiness

- A Prefect flow callable exists at a stable path.
- The callable is referenceable as `path/to/file.py:callable_name`.
- The engine team can provide `REGISTER_FLOW_SOURCE`.
- The engine team can provide `REGISTER_FLOW_ENTRYPOINT`.
- Import-time dependencies for the flow are available in the registration runtime.

## 2) Flow parameter compatibility

- The flow accepts `job_spec_json`.
- The flow accepts optional `resume_key`.
- The flow accepts optional `checkpoint_dir`.
- The flow parameter schema matches the deployment schema expected by the orchestrator.

## 3) Job spec compatibility

- `job_spec_json` is compatible with [job_spec.py](/home/esillileu/discoverex/orchestrator/src/flows/job_spec.py).
- `repo_url` and `ref` work for `run_mode=repo`.
- `entrypoint` is non-empty and deterministic.
- `config` paths are repository-relative only.
- `inputs` can be parsed from `ORCH_JOB_INPUTS_JSON`.

## 4) Runtime compatibility

- The engine runs non-interactively.
- The engine exits on its own.
- The exit code reflects success or failure.
- The engine tolerates execution from a temp workdir.
- The engine tolerates worker-injected environment variables.

## 5) Auth and storage boundary

- The engine does not require Prefect auth headers.
- The engine does not require MinIO credentials.
- The engine does not require MLflow DB credentials.
- The engine uses `MLFLOW_TRACKING_URI` as provided.
- The engine does not depend on direct Cloudflare Access headers for MLflow.

## 6) Durable output expectation

- The engine team understands that only worker-managed artifacts are durable today by default.
- If durable engine-owned artifacts are required, the engine writes them under `ORCH_ENGINE_ARTIFACT_DIR`.
- The engine writes `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH` when durable engine-owned artifacts exist.
- Manifest paths are relative and stay under the worker-provided artifact directory.
- MLflow tags are used for metadata linkage, not artifact byte transport.

## 7) Deployment routing compatibility

- The engine can be registered as `e2e-test`.
- The engine can be registered as `e2e-test-colab`.
- If needed, compatibility aliases `e2e-test-legacy` and `e2e-test-colab-legacy` are supported during cutover.
- The deployment is routed to queues that actual workers are polling.

## 8) Validation

- Registration succeeds in Prefect.
- A flow run can be created successfully.
- Worker execution reaches a terminal state.
- `stdout.log`, `stderr.log`, `result.json`, and `artifacts.json` exist in storage.
- if engine-owned artifacts are declared, `engine-artifacts.json` and declared engine objects exist in storage.
- If MLflow is used, the run can be found and read back.
