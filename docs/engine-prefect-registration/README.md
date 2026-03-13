# Engine Registration Requirements

This directory defines the requirements that an external engine repository must
satisfy so this orchestrator can register and execute the engine's Prefect flow.

The engine is assumed to live in a separate repository. Registration is still
performed from this orchestrator repository, but the engine repo must provide a
compatible flow source, callable, and runtime contract.

Start here, then read the companion docs in this same directory:

- requirements overview:
  [README.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/README.md)
- runtime env and auth boundary:
  [runtime-auth-and-env.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/runtime-auth-and-env.md)
- artifact persistence contract:
  [artifact-persistence-contract.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/artifact-persistence-contract.md)
- worker-managed output directory contract:
  [worker-managed-output-directory-contract.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/worker-managed-output-directory-contract.md)
- implementation checklist:
  [implementation-checklist.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/implementation-checklist.md)
- registration handoff form:
  [register.engine.env.example](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/register.engine.env.example)
- example submit payload:
  [job_spec.repo.example.json](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/job_spec.repo.example.json)
- example engine artifact manifest:
  [engine-artifacts.manifest.example.json](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/engine-artifacts.manifest.example.json)

## 1) Scope

This is a contract for the engine repository, not an operator runbook for this
repository.

The engine team is responsible for:

- exposing a registerable Prefect flow callable
- keeping that flow's parameter schema compatible with the orchestrator
- keeping the engine repo layout and dependencies executable by workers
- providing the source location and entrypoint needed for registration

This repository is responsible for:

- calling the registrar
- creating deployments in Prefect
- routing deployments to the expected pool and queues
- submitting `job_spec_json` payloads to those deployments

## 1.1 Responsibility boundary

The external engine repo owns:

- engine source code and dependency graph
- Prefect flow callable exposed for registration
- compatibility of that flow's parameter schema
- engine process behavior after the worker launches the entrypoint

This orchestrator owns:

- Prefect deployment creation and refresh
- worker scheduling via pool and queue selection
- repository checkout for `repo` mode jobs
- runtime environment injection for the child process
- artifact upload orchestration
- storage and MLflow access mediation

The worker is the boundary component between orchestration and engine runtime.

The engine must not assume ownership of:

- Prefect API authentication details
- storage presign APIs
- object-store credentials
- MLflow backend address or database credentials
- Cloudflare Access header injection

For durable engine-owned artifacts, the official storage contract is:

- engine writes files into `ORCH_ENGINE_ARTIFACT_DIR`
- engine writes `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- worker uploads those files after execution

## 2) Required engine deliverables

The external engine repo must provide all of the following.

### 2.1 Registerable flow callable

The repo must expose a Prefect flow callable that can be referenced as:

- `path/to/file.py:callable_name`

Examples:

- `src/flows/my_engine_flow.py:my_engine_flow`
- `engine/prefect_flow.py:run_job_flow`

The orchestrator registrar passes this value as `REGISTER_FLOW_ENTRYPOINT`.

### 2.2 Source root visible to the registrar

The engine repo must be made visible to the registration runtime at a stable
source root.

Examples:

- `/app`
- `/workspace/engine`
- mounted git checkout path inside a container

The orchestrator registrar passes this value as `REGISTER_FLOW_SOURCE`.

### 2.3 Compatible flow signature

If the engine flow is intended to replace the current compatibility wrapper
without changing submitters, its live Prefect flow signature must accept:

- `job_spec_json`
- `resume_key` optional
- `checkpoint_dir` optional

Current compatible reference:

- [src/flows/engine_run/flow.py](/home/esillileu/discoverex/orchestrator/src/flows/engine_run/flow.py)

Contract rule:

- the registered deployment parameter schema must match the live flow signature

If the engine flow exposes a different signature, this repository's submit and
observability paths will need coordinated changes.

### 2.4 Job spec compatibility

The engine flow must accept `job_spec_json` values that validate against:

- [src/flows/job_spec.py](/home/esillileu/discoverex/orchestrator/src/flows/job_spec.py)

Reference payload:

- [job_spec.repo.example.json](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/job_spec.repo.example.json)

Required minimum payload shape:

```json
{
  "engine": "my-engine",
  "repo_url": "https://github.com/example/engine.git",
  "ref": "main",
  "entrypoint": ["python", "-m", "engine.main"]
}
```

### 2.5 Worker execution compatibility

The engine repo must remain runnable under the worker contract documented in:

- [docs/dev/engine-implementation-contract.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-implementation-contract.md)

In practice this means:

- non-interactive entrypoint
- repo checkout works from `repo_url` and `ref`
- worker can run the declared command in a temp workdir
- engine tolerates orchestrator-provided environment variables
- engine does not require direct object-store credentials

## 2.6 Worker-provided runtime environment

Before the engine process starts, the worker injects runtime variables including:

- `ORCH_ENGINE`
- `ORCH_RUN_MODE`
- `ORCH_FLOW_RUN_ID`
- `ORCH_ATTEMPT`
- `ORCH_OUTPUTS_PREFIX`
- `ORCH_RESOLVED_COMMIT`
- `ORCH_JOB_INPUTS_JSON`

Conditionally injected:

- `ORCH_JOB_NAME`
- `ORCH_JOB_CONFIG_PATH`

The engine may also receive additional environment values from `job_spec.env`.

Reference implementation:

- [src/runner/entrypoint/core.py](/home/esillileu/discoverex/orchestrator/src/runner/entrypoint/core.py)

## 2.7 Worker-managed auth and proxy behavior

The engine should treat service authentication as worker-managed unless the
worker explicitly exposes a worker-facing public endpoint.

### Prefect

The engine does not talk to Prefect directly for normal job execution.
Prefect auth is handled by the register path, worker, submitter, and
observability tooling.

### Storage

The engine should not call storage presign APIs or upload orchestration
artifacts directly.

The worker owns:

- `STORAGE_API_URL`
- Cloudflare Access headers for storage-api
- presign requests
- signed object URL uploads

### MLflow

If the engine writes MLflow metadata, it should use only the exposed
`MLFLOW_TRACKING_URI`.

When the tracking URI is a remote HTTP(S) endpoint and Cloudflare Access is
required, the worker may start a local proxy and rewrite `MLFLOW_TRACKING_URI`
for the child process.

Important boundary rules:

- the engine should use `MLFLOW_TRACKING_URI` as given
- the engine should not depend on Cloudflare Access headers directly
- the engine should not require backend MLflow container addresses
- the worker strips `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` before
  launching the engine when proxying MLflow

Reference implementation:

- [src/runner/mlflow_proxy.py](/home/esillileu/discoverex/orchestrator/src/runner/mlflow_proxy.py)
- [docs/dev/service-auth-model.md](/home/esillileu/discoverex/orchestrator/docs/dev/service-auth-model.md)

## 3) Deployment naming requirements

Unless there is a coordinated cutover, the engine flow must be registered under
the deployment names already expected by this repository.

Required names:

- fixed primary: `e2e-test`
- colab primary: `e2e-test-colab`

Compatibility aliases during cutover:

- fixed alias: `e2e-test-legacy`
- colab alias: `e2e-test-colab-legacy`

Current flow name expected in Prefect UI:

- `e2e-job`

That yields deployment identifiers such as:

- `e2e-job/e2e-test`
- `e2e-job/e2e-test-colab`

If these names change, at minimum the following paths must be reviewed:

- [scripts/ops/prefect_submit_router.py](/home/esillileu/discoverex/orchestrator/scripts/ops/prefect_submit_router.py)
- [scripts/observability/prefect_fixed_dummy_smoke.py](/home/esillileu/discoverex/orchestrator/scripts/observability/prefect_fixed_dummy_smoke.py)
- [docs/dev/service-contracts.md](/home/esillileu/discoverex/orchestrator/docs/dev/service-contracts.md)

## 4) Registration input form

The engine team must hand the following values to whoever operates
registration from this repository.

Use [register.engine.env.example](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/register.engine.env.example)
as the handoff form.

Fields the engine repo must supply:

- `REGISTER_FLOW_SOURCE`
- `REGISTER_FLOW_ENTRYPOINT`
- optional `REGISTER_DEPLOYMENT_VERSION`

Fields normally fixed by orchestrator operations:

- `PREFECT_API_URL`
- `PREFECT_WORK_POOL`
- deployment names
- queue names
- access headers and service tokens

## 4.1 Registration method expected by this repository

This repository registers the engine flow by resolving:

- `REGISTER_FLOW_SOURCE`
- `REGISTER_FLOW_ENTRYPOINT`

into:

```python
flow.from_source(source=..., entrypoint=...)
```

It then deploys that flow into the configured Prefect work pool and work
queues.

That means the engine repo must provide:

- a source tree readable from the registration runtime
- an importable Prefect flow callable at the declared entrypoint
- any import-time dependencies required to load that flow

## 5) What this repository will do with those inputs

This repository currently registers deployments by:

1. loading the engine flow from `flow.from_source(source=..., entrypoint=...)`
2. creating deployments in the configured pool and queues
3. submitting `job_spec_json` to those deployments later

Canonical registration implementation:

- [src/deployments/register/main.py](/home/esillileu/discoverex/orchestrator/src/deployments/register/main.py)
- [infra/images/entrypoints/register-entrypoint.sh](/home/esillileu/discoverex/orchestrator/infra/images/entrypoints/register-entrypoint.sh)

The engine repo does not need to copy this repository's register scripts. It
needs only to satisfy the input contract those scripts consume.

## 5.1 Job execution path after deployment registration

Once the deployment exists, this repository executes jobs as follows:

1. submitter sends `job_spec_json` to the deployment
2. Prefect places the run on the configured pool and queue
3. worker polls and claims the flow run
4. flow validates `job_spec_json`
5. worker prepares repo checkout or inline execution context
6. worker injects runtime env and launches the engine entrypoint
7. worker captures `stdout.log`, `stderr.log`, `result.json`
8. worker uploads artifacts through storage-api
9. engine may write MLflow metadata through the worker-facing tracking URI

The engine repo must be compatible with the entire path above, not only the
registration step.

## 5.2 Required job spec and execution method

Normal execution is driven by a `job_spec_json` payload. The primary supported
mode for an external engine repo is `run_mode=repo`.

Expected repo-mode fields:

- `engine`
- `repo_url`
- `ref`
- `entrypoint`

Optional fields:

- `config`
- `job_name`
- `inputs`
- `env`
- `outputs_prefix`

Execution model:

- worker clones `repo_url`
- worker resolves `ref` to a concrete commit
- worker checks out the repo into a temp workdir
- worker may run `uv sync` or `uv sync --frozen` when `pyproject.toml` and
  `uv.lock` are present
- worker runs the declared `entrypoint`

The engine should therefore provide:

- a cloneable repository
- a resolvable branch, tag, or commit ref
- a deterministic entrypoint command
- repo-local config paths only

## 5.3 What is persisted today without extra engine-side storage support

With the current worker contract, the following are already persisted without
the engine implementing any direct storage upload logic:

- Prefect flow-run state in Prefect
- `stdout.log`
- `stderr.log`
- `result.json`
- `artifacts.json` manifest for the worker-managed artifacts
- MLflow params, metrics, tags, status, and run metadata written through
  `MLFLOW_TRACKING_URI`

This is enough for:

- deployment registration
- flow execution
- Prefect-side run tracking
- worker-managed execution logs
- worker-managed final result metadata
- MLflow-based progress and run metadata tracking

## 5.4 Current gap: engine-owned durable artifacts

The current contract does not yet define a first-class engine artifact upload
path for arbitrary intermediate files, model outputs, bundles, or scene data
produced during the run.

Today, the worker automatically uploads only:

- `stdout.log`
- `stderr.log`
- `result.json`
- `artifacts.json`

That means the following are not fully specified yet:

- engine-created intermediate artifact files
- engine-created final output files larger than `result.json`
- naming/layout rules for engine-owned objects in MinIO
- how the engine obtains writable object URLs for those files
- how those object URIs are linked back into MLflow or flow results

## 5.5 Recommended artifact contract to add

If the goal is to support external engines that store intermediate and final
artifacts durably on the storage node, one explicit contract still needs to be
added. The clean options are:

### Option A: worker-managed artifact directory upload

The engine writes files into a declared local output directory, and the worker:

- scans that directory after execution
- requests presigned URLs itself
- uploads those files
- records returned `object_uri` values in `artifacts.json`
- optionally mirrors those `object_uri` values into MLflow tags

This keeps presign/auth/storage concerns fully out of the engine.

### Option B: engine-facing storage helper contract

The worker exposes a worker-facing helper or environment contract so the engine
can request presigned URLs indirectly, then upload selected files itself.

If this path is chosen, the contract must define:

- allowed API surface
- auth model
- object naming/layout
- retry behavior
- required MLflow linkage tags

This is more flexible, but it expands the engine/runtime coupling.

## 5.6 Presign support requirement

For the current minimal integration target, the engine does not need direct
presign support.

Direct presign support is unnecessary if the only required durable outputs are:

- worker-managed logs
- `result.json`
- MLflow metadata

Direct or indirect presign support becomes necessary if the engine must persist
additional durable artifacts to MinIO during or after the run.

Recommended default:

- do not require presign support in the engine
- add worker-managed directory upload if durable engine artifacts are required

## 6) Acceptance checklist for an external engine repo

An engine repo is ready for integration when all of the following are true.

1. The repo exposes a Prefect flow callable at a stable source path.
2. The flow callable accepts the required orchestrator parameters.
3. `job_spec_json` is parsed compatibly with [job_spec.py](/home/esillileu/discoverex/orchestrator/src/flows/job_spec.py).
4. The engine entrypoint can run under the worker contract.
5. The engine does not require direct storage credentials, MLflow backend addresses, or Prefect auth details.
6. The engine can operate with worker-managed `MLFLOW_TRACKING_URI` and optional proxy rewriting.
7. The repo owner can provide `REGISTER_FLOW_SOURCE` and `REGISTER_FLOW_ENTRYPOINT`.
8. The flow can be registered under the expected deployment names and queues.

For full durable artifact support beyond logs/result metadata:

9. an explicit engine artifact persistence contract must exist

## 7) Verification after integration

After the engine repo is wired into registration, this repository should verify:

1. the deployment exists in Prefect
2. the deployment is attached to the intended pool and queue
3. a flow run can be created with valid `job_spec_json`
4. the worker can execute the engine successfully

Useful downstream checks:

```bash
prefect deployment ls

./bin/cli observability fixed-dummy-smoke \
  --deployment-name e2e-test \
  --timeout-sec 240
```

## 8) Reference map

Primary handoff files:

- [docs/dev/engine-prefect-registration/README.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/README.md)
- [docs/dev/engine-prefect-registration/runtime-auth-and-env.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/runtime-auth-and-env.md)
- [docs/dev/engine-prefect-registration/artifact-persistence-contract.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/artifact-persistence-contract.md)
- [docs/dev/engine-prefect-registration/worker-managed-output-directory-contract.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/worker-managed-output-directory-contract.md)
- [docs/dev/engine-prefect-registration/implementation-checklist.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/implementation-checklist.md)
- [docs/dev/engine-prefect-registration/register.engine.env.example](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/register.engine.env.example)
- [docs/dev/engine-prefect-registration/job_spec.repo.example.json](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/job_spec.repo.example.json)
- [docs/dev/engine-prefect-registration/engine-artifacts.manifest.example.json](/home/esillileu/discoverex/orchestrator/docs/dev/engine-prefect-registration/engine-artifacts.manifest.example.json)

Related contracts:

- [docs/dev/engine-implementation-contract.md](/home/esillileu/discoverex/orchestrator/docs/dev/engine-implementation-contract.md)
- [docs/dev/service-contracts.md](/home/esillileu/discoverex/orchestrator/docs/dev/service-contracts.md)
