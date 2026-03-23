# Prefect Ops Refactor Execution Brief

This brief translates [PREFECT_OPS_REFACTOR_PLAN.md](/home/esillileu/discoverex/engine/PREFECT_OPS_REFACTOR_PLAN.md) into an execution-focused checklist based on the current repository state.

## Scope

The planned change is not a simple package rename. It is a control-plane refactor that changes:

- Python import paths from `infra.register.*` to `infra.ops.*`
- CLI public surface from mixed `register` and `run obj-sweep|obj-collect` commands to `prefect sweep run|collect`
- default spec locations
- default submitted-manifest locations
- documentation and tests that currently encode the old public surface

The execution/runtime plane in [infra/prefect](/home/esillileu/discoverex/engine/infra/prefect) is expected to stay unchanged.

## Current Baseline

### Existing control-plane package

Current live package: [infra/register](/home/esillileu/discoverex/engine/infra/register)

Top-level modules:

- [infra/register/branch_deployments.py](/home/esillileu/discoverex/engine/infra/register/branch_deployments.py)
- [infra/register/build_job_spec.py](/home/esillileu/discoverex/engine/infra/register/build_job_spec.py)
- [infra/register/check_flow_run_status.py](/home/esillileu/discoverex/engine/infra/register/check_flow_run_status.py)
- [infra/register/collect_naturalness_sweep.py](/home/esillileu/discoverex/engine/infra/register/collect_naturalness_sweep.py)
- [infra/register/collect_object_generation_sweep.py](/home/esillileu/discoverex/engine/infra/register/collect_object_generation_sweep.py)
- [infra/register/deploy_prefect_flows.py](/home/esillileu/discoverex/engine/infra/register/deploy_prefect_flows.py)
- [infra/register/job_types.py](/home/esillileu/discoverex/engine/infra/register/job_types.py)
- [infra/register/naturalness_sweep.py](/home/esillileu/discoverex/engine/infra/register/naturalness_sweep.py)
- [infra/register/object_generation_sweep.py](/home/esillileu/discoverex/engine/infra/register/object_generation_sweep.py)
- [infra/register/register_orchestrator_job.py](/home/esillileu/discoverex/engine/infra/register/register_orchestrator_job.py)
- [infra/register/register_prefect_job.py](/home/esillileu/discoverex/engine/infra/register/register_prefect_job.py)
- [infra/register/settings.py](/home/esillileu/discoverex/engine/infra/register/settings.py)
- [infra/register/submit_job_spec.py](/home/esillileu/discoverex/engine/infra/register/submit_job_spec.py)

### Existing CLI public surface

Current CLI implementation: [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)

Current public surface still includes:

- `./bin/cli prefect deploy flow ...`
- `./bin/cli prefect register flow ...`
- `./bin/cli prefect register batch ...`
- `./bin/cli prefect deploy experiment ...`
- `./bin/cli prefect register experiment-sweep ...`
- `./bin/cli prefect run gen`
- `./bin/cli prefect run obj`
- `./bin/cli prefect run obj-sweep`
- `./bin/cli prefect run obj-collect`

This differs from the target state in the refactor plan.

### Existing package entry points

[pyproject.toml](/home/esillileu/discoverex/engine/pyproject.toml) currently exposes:

- `discoverex-build-job-spec = "infra.register.build_job_spec:main"`
- `discoverex-check-flow-run-status = "infra.register.check_flow_run_status:main"`
- `discoverex-deploy-prefect-flows = "infra.register.deploy_prefect_flows:main"`
- `discoverex-register-orchestrator-job = "infra.register.register_orchestrator_job:main"`
- `discoverex-register-prefect-job = "infra.register.register_prefect_job:main"`
- `discoverex-submit-job-spec = "infra.register.submit_job_spec:main"`

## Stable Rules Already Implemented

These plan assumptions already exist in code and should remain unchanged unless the refactor explicitly changes behavior.

### Purpose to queue mapping

Defined in [infra/register/branch_deployments.py](/home/esillileu/discoverex/engine/infra/register/branch_deployments.py):

- `standard -> gpu-fixed`
- `batch -> gpu-fixed-batch`
- `debug -> gpu-fixed-debug`
- `backfill -> gpu-fixed-backfill`

### Purpose-scoped deployment naming

Also defined in [infra/register/branch_deployments.py](/home/esillileu/discoverex/engine/infra/register/branch_deployments.py):

- `discoverex-generate-<purpose>`
- `discoverex-verify-<purpose>`
- `discoverex-animate-<purpose>`
- `discoverex-combined-<purpose>`

### Execution/runtime plane boundary

Documented in:

- [docs/ops/runtime.md](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- [docs/contracts/registration/README.md](/home/esillileu/discoverex/engine/docs/contracts/registration/README.md)

Expected invariant:

- keep [infra/prefect](/home/esillileu/discoverex/engine/infra/prefect) unchanged
- keep [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py) as the public flow-callable surface

## Recommended File Mapping

The plan gives target directories but not a file-level migration map. The following mapping is the minimum concrete translation needed before implementation starts.

### Shared

- `infra/register/settings.py` -> `infra/ops/shared/settings.py`
- `infra/register/job_types.py` -> `infra/ops/shared/job_types.py`
- `infra/register/branch_deployments.py` -> `infra/ops/shared/deployments.py`
- `infra/register/build_job_spec.py` -> `infra/ops/shared/build_job_spec.py`
- `infra/register/check_flow_run_status.py` -> `infra/ops/shared/check_flow_run_status.py`

### Deploy

- `infra/register/deploy_prefect_flows.py` -> `infra/ops/deploy/deploy_prefect_flows.py`

### Standard submitters

- `infra/register/register_orchestrator_job.py` -> `infra/ops/submitters/register_orchestrator_job.py`
- `infra/register/register_prefect_job.py` -> `infra/ops/submitters/register_prefect_job.py`
- `infra/register/submit_job_spec.py` -> `infra/ops/submitters/submit_job_spec.py`

### Sweep submitters

- `infra/register/object_generation_sweep.py` -> `infra/ops/submitters/object_generation_sweep.py`
- `infra/register/naturalness_sweep.py` -> `infra/ops/submitters/naturalness_sweep.py`

### Collectors

- `infra/register/collect_object_generation_sweep.py` -> `infra/ops/collectors/object_generation_sweep.py`
- `infra/register/collect_naturalness_sweep.py` -> `infra/ops/collectors/naturalness_sweep.py`

### Specs and manifests

- `infra/register/job_specs/...` -> `infra/ops/specs/job/...`
- `infra/register/sweeps/...` -> `infra/ops/specs/sweep/...`
- repo-managed submitted manifests -> `infra/ops/manifests/<sweep-id>.submitted.json`

### Candidate archive items

These should not stay mixed into the live control plane without an explicit reason:

- `infra/register/quick_generate.sh`
- existing checked-in `*.submitted.json` files under [infra/register/sweeps](/home/esillileu/discoverex/engine/infra/register/sweeps)

## Existing Sweep Behavior That Must Be Preserved Or Replaced Deliberately

### Object-quality sweep

Submitter: [infra/register/object_generation_sweep.py](/home/esillileu/discoverex/engine/infra/register/object_generation_sweep.py)

Current behavior:

- builds a manifest from one scenario plus a parameter grid
- writes submission records keyed by `policy_id` and `scenario_id`
- supports queue override via `--work-queue-name`
- supports retry of missing or unsubmitted work via `--retry-missing-limit`
- collector classifies missing submitted runs as `failed_to_collect`
- collector classifies `not_submitted`, `pending`, `failed`, `cancelled`, `failed_to_collect`

Tests encoding this behavior:

- [tests/test_object_generation_sweep.py](/home/esillileu/discoverex/engine/tests/test_object_generation_sweep.py)

### Naturalness sweep

Submitter: [infra/register/naturalness_sweep.py](/home/esillileu/discoverex/engine/infra/register/naturalness_sweep.py)

Current behavior:

- builds manifests from scenarios or `scenarios_csv`
- supports parameter grids
- supports `variant_pack` and `case_per_run`
- uses `policy_id`, `scenario_id`, and variant metadata
- defaults deployment suffix to experiment-style naming

Collector: [infra/register/collect_naturalness_sweep.py](/home/esillileu/discoverex/engine/infra/register/collect_naturalness_sweep.py)

Current collector is much simpler than the object-quality collector:

- reads local case files only
- aggregates per-policy naturalness metrics
- does not currently do the same Prefect state and remote artifact recovery work as the object-quality collector

Tests encoding submitter behavior:

- [tests/test_naturalness_sweep.py](/home/esillileu/discoverex/engine/tests/test_naturalness_sweep.py)

This asymmetry matters because the refactor plan assumes a common `collectors/` layer with shared run-state and result classification helpers.

## Main Impact Areas

### CLI and public guidance

Files tied to the old surface:

- [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)
- [docs/ops/cli.md](/home/esillileu/discoverex/engine/docs/ops/cli.md)
- [docs/ops/object-quality-sweeps.md](/home/esillileu/discoverex/engine/docs/ops/object-quality-sweeps.md)
- [infra/register/sweeps/README.md](/home/esillileu/discoverex/engine/infra/register/sweeps/README.md)
- [docs/contracts/registration/README.md](/home/esillileu/discoverex/engine/docs/contracts/registration/README.md)
- [README.md](/home/esillileu/discoverex/engine/README.md)

Old commands that need removal or migration:

- `prefect run obj-sweep`
- `prefect run obj-collect`
- `prefect register experiment-sweep`

### Tests and imports

Files directly encoding `infra.register.*` imports or old CLI expectations:

- [tests/test_scripts_cli_prefect.py](/home/esillileu/discoverex/engine/tests/test_scripts_cli_prefect.py)
- [tests/test_register_prefect_job_script.py](/home/esillileu/discoverex/engine/tests/test_register_prefect_job_script.py)
- [tests/test_register_orchestrator_job_script.py](/home/esillileu/discoverex/engine/tests/test_register_orchestrator_job_script.py)
- [tests/test_deploy_prefect_flows_script.py](/home/esillileu/discoverex/engine/tests/test_deploy_prefect_flows_script.py)
- [tests/test_submit_job_spec_script.py](/home/esillileu/discoverex/engine/tests/test_submit_job_spec_script.py)
- [tests/test_object_generation_sweep.py](/home/esillileu/discoverex/engine/tests/test_object_generation_sweep.py)
- [tests/test_naturalness_sweep.py](/home/esillileu/discoverex/engine/tests/test_naturalness_sweep.py)

### Checked-in docs that state `infra/register` as source of truth

- [docs/dev/prefect-migration.md](/home/esillileu/discoverex/engine/docs/dev/prefect-migration.md)
- [docs/ops/runtime.md](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- [docs/contracts/registration/README.md](/home/esillileu/discoverex/engine/docs/contracts/registration/README.md)
- [README.md](/home/esillileu/discoverex/engine/README.md)

## Missing Decisions That Should Be Locked Before Large-Scale Edits

The plan is directionally clear, but these items are still underspecified for implementation.

### 1. Sweep spec resolution contract

Locked decision:

- input is always `--sweep-spec <yaml path>`
- the sweep spec path is the source of truth for the new CLI surface
- an explicit `sweep_kind` field is not required for this refactor pass
- the new SSOT path is the object-quality sweep family
- other sweep families are legacy and out of scope for the primary new flow

### 2. Shared collector contract

The plan assumes shared state classification across sweep types, but current collectors are not symmetric.

Locked decision:

- the object-quality collector behavior is the SSOT for the new path
- other sweep families remain legacy in this pass
- shared collector work should be extracted only insofar as it supports the object-quality path cleanly

### 3. Manifest merge semantics

The plan says repeated `sweep run` should merge state, but it does not define:

- whether latest record always wins
- whether terminal successful records are immutable
- whether manual manifest edits are preserved

Locked decision:

- key manifest rows by `sweep_id`, `policy_id`, `scenario_id`
- overwrite only retry-target runtime fields on resubmission:
  - `flow_run_id`
  - `submitted`
  - `status`
  - optionally `deployment`
  - optionally `updated_at`
- preserve the rest of the manifest row contents

### 4. `--limit N` selection order

The plan defines eligibility but not stable ordering.

Locked decision:

- preserve source manifest job order
- filter to retry-eligible rows
- take first `N`

### 5. Treatment of checked-in submitted manifests

Current tree contains checked-in `*.submitted.json` files under live sweep spec directories.

Locked decision:

- keep the same submitted-manifest contract shape
- relocate submitted-manifest files under `infra/ops/manifests/`
- do not change the contract during this refactor pass

## Suggested Execution Order

### Phase 1: create new structure without behavior change

1. Create `infra/ops` package layout.
2. Move shared, deploy, submitter, and collector modules to the new layout.
3. Update internal imports.
4. Update `pyproject.toml` entry points to `infra.ops.*`.

### Phase 2: cut CLI to the new public surface

1. Refactor [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py) so:
   - `prefect run gen|obj` remain
   - `prefect sweep run|collect` become the only supported sweep entrypoints
2. Remove old sweep routes from docs and tests.

### Phase 3: move specs and manifests

1. Move job specs to `infra/ops/specs/job`.
2. Move sweep specs to `infra/ops/specs/sweep`.
3. Introduce `infra/ops/manifests`.
4. Change default manifest path resolution to `infra/ops/manifests/<sweep-id>.submitted.json`.

### Phase 4: normalize sweep collection behavior

1. Extract shared result classification helpers.
2. Make object-quality and naturalness collectors conform to the same result model.
3. Add tests for:
   - default manifest path derivation
   - merge behavior
   - `--limit N`
   - retry eligibility

### Phase 5: remove old references completely

1. Remove remaining `infra.register.*` imports.
2. Remove or archive obsolete files.
3. Update docs and contracts to point at `infra/ops`.

## Validation Checklist

At minimum, the refactor should be considered incomplete until all of the following pass:

- `rg -n "infra\\.register" .`
- `uv run pytest tests/test_scripts_cli_prefect.py`
- `uv run pytest tests/test_object_generation_sweep.py tests/test_naturalness_sweep.py`
- `uv run pytest tests/test_register_prefect_job_script.py tests/test_register_orchestrator_job_script.py tests/test_submit_job_spec_script.py tests/test_deploy_prefect_flows_script.py`

Additional doc sanity checks:

- `rg -n "obj-sweep|obj-collect|experiment-sweep|infra/register" README.md docs infra scripts tests pyproject.toml`

## Working Tree Note

Before implementation, reconcile unrelated in-progress changes already present in the working tree:

- modified: [docs/ops/cli.md](/home/esillileu/discoverex/engine/docs/ops/cli.md)
- modified: [infra/register/job_specs/generate_verify.standard.yaml](/home/esillileu/discoverex/engine/infra/register/job_specs/generate_verify.standard.yaml)
- modified: [infra/register/sweeps/README.md](/home/esillileu/discoverex/engine/infra/register/sweeps/README.md)
- modified: [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)
- modified: [tests/test_scripts_cli_prefect.py](/home/esillileu/discoverex/engine/tests/test_scripts_cli_prefect.py)
- untracked: [PREFECT_OPS_REFACTOR_PLAN.md](/home/esillileu/discoverex/engine/PREFECT_OPS_REFACTOR_PLAN.md)
- untracked: [docs/ops/object-quality-sweeps.md](/home/esillileu/discoverex/engine/docs/ops/object-quality-sweeps.md)

This refactor touches several of the same files, so those changes should be reviewed before starting the actual code move.
