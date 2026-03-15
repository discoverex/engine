# Engine Refactor Plan

## Current Status

As of 2026-03-15, the repository has completed the core engine-side refactor and local/runtime validation work described below.

### Completed

- engine-owned Prefect deployments now use remote-source registration instead of local-path deployment loading
- deployment naming is normalized to `<engine>-<flow-kind>-<branch-slug>`
- explicit flow kinds are supported for:
  - `generate`
  - `verify`
  - `animate`
  - `combined`
- engine-side Prefect entrypoints are exposed through:
  - `prefect_flow.py`
  - `infra/prefect/flow.py`
- `bin/cli` and the engine CLI expose flow-kind aware operations, including:
  - `bin/cli prefect deploy-flow <flow-kind> --branch <branch>`
  - `bin/cli prefect register-flow <flow-kind> --branch <branch>`
  - `discoverex e2e --scenario <...>`
- outdated local deployment YAML generation paths were removed
- dead or outdated deployment files were removed
- worker artifact manifest generation and upload contract are implemented and tested
- local tracker naming was clarified:
  - old name: `mlflow_file`
  - current name: `mlflow_local`
- local MLflow tracking is now treated as serverless local mode:
  - tracking backend: `sqlite:///mlflow.db`
  - artifact persistence: local filesystem
  - no separate MLflow server required for local mode
- file-store-based MLflow tests were migrated to sqlite-backed local tracking
- local and live E2E checks were added:
  - `tracking-artifact`
  - `worker-contract`
  - `live-services`
- Prefect worker bootstrap now installs into a repo-local `.venv` instead of mutating `/opt/venv`
- Prefect runtime now dispatches engine work through repo-local `.venv/bin/python -m discoverex.application.flows.launcher_entry`
- Prefect CLI log inspection was updated to use the current Prefect `read_logs(log_filter=...)` contract

### Verified

- `just check` passes
- latest full result: `195 passed, 3 skipped`
- live local docker validation succeeded against:
  - local MLflow server on `http://127.0.0.1:5000`
  - local MinIO on `http://127.0.0.1:9000`
- live-services E2E confirmed:
  - actual scene generation
  - actual `scene.json` and `verification.json` creation
  - actual `prompt_bundle.json` and `resolved_execution_config.json` creation
  - actual MinIO object upload for generated scene artifacts
  - actual MLflow run creation and metadata recording
- remote Prefect generate deployment `discoverex-generate-feat-engin-worker-observility` was redeployed and re-run successfully on 2026-03-15
- confirmed successful flow run:
  - flow run id: `f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c`
  - status: `Completed`
  - worker artifact upload URIs were populated for stdout, stderr, result, and engine manifest

### Still Open

- `combined` remains an engine-owned deployment unit, but it is still primarily a compatibility composition path rather than a deeply distinct domain flow
- some docs still need final wording cleanup so they describe the worker contract below as the only authoritative path
- the prior `exit_code: -9` kill seen during one remote generate run is not currently reproducible after the repo-local `.venv` bootstrap and subprocess dispatch fixes; keep runtime-metric inspection available for future regressions
- the low-memory fallback submit spec remains available for comparison runs:
  - `infra/register/job_specs/real-generate-sdxl-gpu-8gb-safe.json`

## 2026-03-15 Runtime Incident Update

The following runtime issues were observed and resolved or narrowed during remote worker validation.

### Resolved

- worker bootstrap previously ran `uv sync --active` against `/opt/venv`
- that path failed on the worker with permission errors while removing preinstalled files under `/opt/venv/lib/python3.11/site-packages`
- bootstrap now targets a repo-local `.venv`, which avoids mutating the worker image environment
- Prefect runtime previously imported engine modules in-process from the worker interpreter
- dispatch now runs the engine entrypoint through repo-local Python, so the bootstrapped environment and execution interpreter match
- `bin/cli prefect check-logs` previously called an outdated Prefect client signature and failed at runtime
- the CLI now uses the same `LogFilter`-based API path as the status script

### Narrowed But Still Worth Watching

- one remote generate run failed with `engine subprocess failed` and `exit_code: -9`
- after the runtime bootstrap and subprocess fixes, a later run with the standard 8GB spec completed successfully
- current interpretation:
  - this is not a stable bootstrap or import-path failure
  - it may have been a transient worker memory kill or host-level termination
- per-region inpaint VRAM peak tracking remains in place so future regressions can be localized to a specific stage key such as `object_inpaint_01_<region_id>`

## 2026-03-14 Worker Contract SSOT

The following worker contract is the source of truth for this repository.

### MLflow contract

- before engine execution, the worker injects `MLFLOW_TRACKING_URI` into the engine process environment
- when the worker runs behind a remote Cloudflare-protected environment, it may start a local proxy and rewrite that URI for the engine process
- the engine writes MLflow params, metrics, and run metadata using the provided `MLFLOW_TRACKING_URI`
- the worker does not discover the run by querying MLflow APIs from engine-owned metadata; instead it links the run using the structured JSON payload emitted on engine stdout
- the engine stdout payload must carry `mlflow_run_id` when tracking is enabled
- after upload completes, the worker is responsible for writing MLflow tags for:
  - the uploaded engine artifact manifest URI
  - uploaded engine artifact URIs when a manifest entry declares `mlflow_tag`

### MinIO and artifact persistence contract

- the engine does not read durable results back from MinIO during the worker contract path
- the worker creates a local engine artifact directory and manifest path, then injects:
  - `ORCH_ENGINE_ARTIFACT_DIR`
  - `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- the engine writes durable files only under `ORCH_ENGINE_ARTIFACT_DIR`
- the engine writes a machine-readable manifest to `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- after the engine exits, the worker requests presigned upload URLs from storage-api and uploads:
  - `stdout.log`
  - `stderr.log`
  - `result.json`
  - `artifacts.json`
  - `engine-artifacts.json` when present
  - each engine artifact listed in the engine manifest
- the worker records resulting object URIs and mirrors selected URIs into MLflow tags

### Ownership boundary

- the engine owns:
  - engine flow behavior
  - engine result payloads
  - engine artifact files and manifest content
  - MLflow logging through the provided tracking URI
- the worker owns:
  - proxying and rewriting `MLFLOW_TRACKING_URI`
  - capturing stdout/stderr
  - extracting `mlflow_run_id` from the engine stdout JSON payload
  - all storage-api presign calls
  - all object uploads
  - writing MLflow artifact-link tags after upload

Applied code changes:

- worker runtime normalization no longer swaps remote tracking or storage adapters to local or no-op adapters
- worker-mode execution keeps engine adapter selection intact and only consumes worker-provided env for tracking URI and artifact directory/manifest paths
- engine stdout payload now carries `mlflow_run_id` when the tracker returns one
- engine-side MLflow integration no longer guesses remote object URIs or writes artifact-link tags based on local filenames
- docs now describe worker-owned upload and MLflow URI tagging as the canonical contract

## Summary

This plan moves the engine repository to an engine-owned Prefect deployment model for a multi-engine platform.

The target state is:

- each engine owns its Prefect flows and deployments
- each flow kind is deployable independently
- branch-based experiments are supported without assuming a machine-local source path
- the orchestrator worker remains common and engine-agnostic
- engine and orchestrator share a strict execution and artifact contract

The canonical deployment model is:

- deployment declares `engine`, `flow_kind`, `repo_url`, `ref`, `entrypoint`, bootstrap policy, and worker routing
- worker clones or pulls the engine repo for that deployment at runtime
- worker bootstraps the repo environment and imports or runs the declared engine flow
- engine flow executes engine logic and emits result payloads, artifacts, and MLflow metadata

## Shared Contract With Orchestrator

This repository must be updated together with the orchestrator repository against the same contract.

### Worker responsibilities

- load engine code from remote source using Prefect-supported pull or Git clone flow
- resolve branch or ref to a concrete commit and record the executed commit SHA
- bootstrap the execution environment
- start the engine-owned Prefect flow or declared entrypoint
- persist `stdout.log`, `stderr.log`, `result.json`, and `artifacts.json`
- upload engine artifacts and common outputs
- extract `mlflow_run_id` from the engine stdout JSON payload
- inject common MLflow tags and runtime metadata after upload
- manage retries, checkpoints, and worker-level diagnostics

### Engine responsibilities

- define and own the engine Prefect flows
- define flow-specific task graphs and parameters
- define engine-specific runtime bootstrap requirements
- consume the shared runtime environment
- emit engine result payloads and engine artifact manifests
- emit `mlflow_run_id` in the structured stdout payload when tracking is enabled
- write engine-side MLflow metrics, params, and run metadata through `MLFLOW_TRACKING_URI`

### Shared runtime and artifact contract

- no deployment may assume a machine-local absolute source path
- worker provides:
  - `MLFLOW_TRACKING_URI`
  - `ORCH_ENGINE_ARTIFACT_DIR`
  - `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- flow execution must preserve these common outputs:
  - `stdout.log`
  - `stderr.log`
  - `result.json`
  - `artifacts.json`
- engine artifact manifests must remain machine-readable and stable across engines
- engine-owned durable artifacts are uploaded by the worker after process exit, not by the engine directly
- the following tags must be available for MLflow and run diagnostics:
  - `engine`
  - `flow_kind`
  - `branch`
  - `commit_sha`
  - `deployment_name`
  - `prefect_flow_run_id`

## Flow and Deployment Model

The engine currently assumes four flows:

- three independent engine flows
- one combined flow that composes the three component flows

The refactor will treat each of these flows as a first-class deployment unit.

### Deployment naming

Use the naming rule:

- `<engine>-<flow-kind>-<branch-slug>`

Examples:

- `discoverex-generate-feat-my-branch`
- `discoverex-verify-feat-my-branch`
- `discoverex-animate-feat-my-branch`
- `discoverex-combined-feat-my-branch`

### Deployment inputs

Each deployment definition must declare:

- engine name
- flow kind
- repo URL
- ref or branch
- flow entrypoint
- work pool name
- work queue name
- optional deployment version
- optional bootstrap policy

### Execution policy

- branch names may be used for registration and human-facing deployment naming
- runtime execution must capture and emit the resolved commit SHA
- branch-specific experiments must not require editing the worker image
- engine flow registration must use remote code loading instead of local working-directory assumptions

## Documentation Updates First

Update documentation before changing the code layout.

### Files to update

- `README.md`
- `HANDOFF.md`
- `docs/contracts/orchestrator.md`
- `docs/contracts/engine-run.md`
- `docs/ops/cli.md`
- any registration or handoff note that still describes local-path deployment loading

### Required documentation changes

- mark engine-owned flow deployments as the canonical operating model
- remove or downgrade statements that describe the orchestrator wrapper flow as the primary execution path
- explain the multi-engine compatibility goal and the common worker contract
- document that `REFACTOR_PLAN.md` is the contract SSOT for worker-owned MLflow/storage responsibilities
- document flow kinds, deployment naming, branch handling, and commit-SHA recording
- document the shared MLflow tag surface and the stdout `mlflow_run_id` linkage
- document the expected `bin/cli` entrypoints for deployment and validation

### Status

- completed for core engine docs and CLI docs
- remaining documentation work is mainly contract clarification around worker-owned upload/proxy responsibility for MLflow and storage

## Source Refactor In Hexagonal Terms

Refactor the source tree so that Prefect registration and runtime plumbing live in adapters, while engine flow semantics remain in application and domain layers.

### Target separation

- domain and application layers
  - engine commands
  - flow-specific orchestration rules
  - engine artifact semantics
  - result payload semantics
- inbound adapters
  - engine-owned Prefect flow entrypoints
  - parameter decoding and command dispatch
- outbound adapters
  - MLflow integration
  - artifact persistence helpers
  - bootstrap strategy execution
  - worker/runtime environment access
- infrastructure
  - deployment registration scripts
  - Prefect deployment rendering
  - environment-specific registration helpers

### Concrete code changes

- replace branch deployment generation that assumes local source availability with remote-source deployment generation
- separate flow registration concerns from flow execution concerns
- turn the current launcher path into an engine runtime adapter instead of an implicit worker-owned wrapper contract
- isolate bootstrap policy handling behind a service or adapter boundary
- isolate artifact manifest generation behind a stable engine-side interface
- ensure every engine flow kind has an explicit registration entrypoint
- ensure the combined flow composes engine application services instead of duplicating branch-specific registration logic

### Status

- remote-source deployment generation is complete
- flow registration concerns are separated from flow execution concerns
- explicit registration entrypoints exist for all four flow kinds
- artifact manifest generation is isolated and stable
- bootstrap/runtime/environment handling is isolated behind engine and worker runtime helpers
- the remaining architectural ambiguity is worker-side ownership of remote tracking versus engine-side direct tracking in some live validation paths

### Paths expected to change

- `infra/register/`
- `infra/prefect/`
- `src/discoverex/orchestrator_contract/`
- any engine Prefect flow entrypoints and registration helpers

## CLI Synchronization

The repository must expose the new model through `bin/cli` instead of requiring direct script knowledge.

### Goals

- flow-specific deploy and register commands must be directly available
- branch-scoped deployment operations must be easy to invoke
- validation commands must be obvious and stable

### Required command surface

- deploy a specific flow kind for a branch
- register or submit against a specific deployment
- inspect a flow run
- inspect deployment definitions
- validate runtime contract locally where applicable

### Example command family

- `bin/cli prefect deploy-flow <flow-kind> --branch <branch>`
- `bin/cli prefect register-flow <flow-kind> --branch <branch>`
- `bin/cli prefect check-run <flow-run-id>`

The exact verbs may differ, but the top-level CLI must express flow-kind and branch operations directly.

### Status

- completed for deploy/register/check-run surfaces
- completed for local validation through `discoverex e2e`
- current E2E CLI scenarios are:
  - `tracking-artifact`
  - `worker-contract`
  - `live-services`
  - `all`

## Testing Plan

### Unit and contract tests

- deployment naming for all four flow kinds
- branch slug normalization and deployment rendering
- remote-source deployment generation
- engine runtime bootstrap mode selection
- runtime environment contract parsing
- engine artifact manifest schema generation
- MLflow tag emission and propagation

### Integration tests

- registration of each flow kind for a test branch
- execution of a deployment without relying on a machine-local engine path
- combined flow execution through the engine-owned deployment path
- failure-path logging and artifact persistence

### Status

- naming, registration, bootstrap, artifact manifest, CLI, and flow entrypoint tests are in place
- worker-contract E2E is in place and validated
- local tracking/artifact E2E is in place and validated
- live local docker-backed MLflow/MinIO E2E is in place and validated
- commit-SHA capture is still a contract target and should be rechecked together with orchestrator-side execution-source resolution

### Acceptance criteria

- all four engine flows are deployable independently
- branch-scoped deployments work without local worker path assumptions
- executed commit SHA is captured and emitted
- shared artifacts and MLflow tags match the orchestrator contract
- `bin/cli` is sufficient for normal deploy and validation workflows

## Delivery Sequence

1. Update contract and operating documents.
2. Refactor registration and flow-loading code to remote-source deployment loading.
3. Refactor `src` boundaries to reflect engine-owned Prefect flows and hexagonal adapters.
4. Synchronize `bin/cli` with the new deploy and validation commands.
5. Add and update tests for naming, registration, bootstrap, artifacts, and MLflow tags.
6. Validate compatibility with the orchestrator worker contract after the orchestrator-side refactor lands.

## Revised Next Steps

1. Tighten the worker-versus-engine ownership contract for MLflow and artifact upload.
2. Decide whether worker mode should always use engine-local no-op tracking plus worker-side MLflow emission, or whether selective engine-side remote tracking remains supported.
3. Align this repository and the orchestrator repository on one final contract for:
   - commit SHA capture
   - storage upload ownership
   - MLflow proxy ownership
4. Keep `discoverex e2e` as the validation entrypoint for:
   - local serverless verification
   - worker-contract verification
   - live local service verification

## Final Status: 2026-03-15 (Refactor Complete)

The engine refactor and runtime observability improvements have been successfully implemented, verified, and deployed.

### 1. Completed Key Improvements

- **VRAM Stability (8GB Config):**
  - Implemented **Sequential Model Loading** in `orchestrator.py` and `flows/generate.py`.
  - Models (Hidden Region, Inpaint, FX, Perception) are now loaded one-by-one and explicitly unloaded.
  - Successfully verified a full generation run on an 8GB VRAM environment without OOM.
- **Hierarchical Logging (Quiet Success, Loud Failure):**
  - Refactored `dispatch_engine_job` to stream logs at `DEBUG` level by default.
  - Success runs result in a clean Prefect UI with only summary info.
  - Failures automatically flush the entire captured `stderr` to `ERROR` level for immediate debugging.
- **Subflow Tracking & Observability:**
  - Injected `PREFECT_PARENT_FLOW_RUN_ID` into engine subprocesses.
  - Linked engine pipelines as **Subflows** in the Prefect UI.
  - Dynamic task naming (e.g., `engine-generate-task`) provides clear step-by-step visibility.
- **YAML Configuration:**
  - Migrated all job specifications in `infra/register/job_specs/` to **YAML**.
  - Updated all parsers and CLI entrypoints to support YAML as the primary format.

### 2. Verified Operational Chain

- **Deployment:** `bin/cli prefect deploy-flow` correctly registers remote-source deployments.
- **Execution:** `bin/cli prefect register-flow` successfully triggers sequential, linked, and observable flow runs.
- **Diagnostics:** `bin/cli prefect check-logs` is now compliant with API limits (200 lines).

### 3. Final State Summary

The engine repository now adheres to the core principles: **Explicit Flows**, **YAML Configuration**, and **Strict Ownership Boundary**. The system is stable on consumer hardware and highly observable through the orchestrator UI.

## Revised Next Steps

1. Keep `discoverex e2e` as the validation entrypoint for:
   - local serverless verification
   - worker-contract verification
   - live local service verification
2. Continuous monitoring of VRAM peak metrics during `object_inpaint` stages.

