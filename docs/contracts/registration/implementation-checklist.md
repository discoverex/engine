# Registration Checklist

Use this checklist when validating registration and worker execution for this repository.

## 1. Flow Exposure

- `prefect_flow.py` exposes the intended callable.
- The callable signature accepts `job_spec_json`, optional `resume_key`, and optional `checkpoint_dir`.
- The selected flow kind matches the intended command surface.

## 2. Registration Path

- `./bin/cli prefect deploy flow <flow-kind> --branch <branch>` succeeds.
- The deployment lands in the intended work pool and queue.
- The deployment name matches purpose-scoped naming rules.

## 3. Submission Path

- `./bin/cli prefect register flow <flow-kind> --branch <branch>` succeeds.
- The submitted `job_spec_json` contains compatible `inputs`.
- Flow kind and command mapping are consistent.

## 4. Worker Runtime

- The worker can import `prefect_flow.py` and `infra/prefect/flow.py`.
- Runtime env includes `MLFLOW_TRACKING_URI` and artifact paths when needed.
- The engine runs non-interactively and terminates with a meaningful exit code.

## 5. Artifact Handling

- Worker-owned artifacts are persisted.
- Engine-owned durable artifacts, if any, are written under `ORCH_ENGINE_ARTIFACT_DIR`.
- The engine manifest is valid when extra durable artifacts exist.

## 6. Validation

- `./bin/cli prefect check-logs <FLOW_RUN_ID>` works for the submitted run.
- `./bin/cli prefect inspect-run <FLOW_RUN_ID>` shows the expected flow/task tree.
- MLflow linkage is visible when tracking is enabled.
