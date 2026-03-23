# Rename `infra/register` To `infra/ops` And Rebuild Prefect Ops Surface

## Summary

Refactor the current Prefect control-plane code from `infra/register` into `infra/ops`, with a hard cutover and no long-lived compatibility wrappers. The new structure should clearly separate deployment management, submission, collection, manifests, and specs. At the same time, simplify the CLI so:

- `prefect run gen|obj` stays standard-job-only
- `prefect sweep run|collect` becomes the sweep entrypoint
- old sweep-specific `register ...sweep` commands are removed or deprecated from the public CLI surface in this pass

State tracking for sweep submissions moves to a dedicated repo-managed directory:
- `infra/ops/manifests/`

## Key Changes

### 1. Rename and restructure `infra/register`

Move implementation into `infra/ops` and split by responsibility.

Recommended structure:

- `infra/ops/deploy/`
  - deployment and queue management
  - purpose naming and queue rules
- `infra/ops/submitters/`
  - single job submitter
  - object sweep submitter
  - naturalness sweep submitter
- `infra/ops/collectors/`
  - sweep collectors
  - shared run-state/result classification helpers
- `infra/ops/specs/job/`
  - current standard and variant job specs
- `infra/ops/specs/sweep/`
  - sweep specs by domain
- `infra/ops/manifests/`
  - submitted manifests and collector state files
- `infra/ops/shared/`
  - settings, common types, naming helpers, shared Prefect client helpers

Hard-cut all Python imports, entry points, tests, docs, and helper scripts from `infra.register.*` to `infra.ops.*`.

### 2. Normalize responsibilities inside `infra/ops`

Make the boundaries explicit:

- deploy manager:
  - own work-pool/queue creation
  - own purpose-based deployment registration
  - own deployment naming/queue rules
- submit manager:
  - own single job submission
  - own sweep expansion and sweep submission
  - own submitted-manifest writing
- collect manager:
  - own run/sweep result recovery
  - own Prefect state classification
  - own aggregate outputs and retry eligibility

Keep `infra/prefect` unchanged as the execution/runtime plane.

### 3. Move specs and manifests to stable locations

Relocate current specs:

- `infra/register/job_specs/...` -> `infra/ops/specs/job/...`
- `infra/register/sweeps/...` -> `infra/ops/specs/sweep/...`

Use:
- `infra/ops/manifests/<sweep-id>.submitted.json`

Behavior:

- `sweep run` writes its state there by default
- `sweep collect` derives the default manifest path from `--sweep-spec`
- users can still override with explicit `--output` or `--submitted-manifest`

Variant tracking remains keyed by:

- `sweep_id`
- `policy_id`
- `scenario_id`
- `flow_run_id`

### 4. Rebuild the Prefect CLI around roles

Keep `prefect run` strictly for standard execution aliases.

Target CLI surface:

- `./bin/cli prefect run gen`
- `./bin/cli prefect run obj`

Add a dedicated sweep group:

- `./bin/cli prefect sweep run --sweep-spec <path>`
- `./bin/cli prefect sweep collect --sweep-spec <path>`

`prefect sweep run` behavior:

- submit one sweep spec
- default manifest path: `infra/ops/manifests/<sweep-id>.submitted.json`
- supports `--deployment`, `--purpose`, `--work-queue-name`
- supports `--limit N`
- when `--limit N` is set, only submit up to `N` entries that are:
  - `not_submitted`
  - `failed`
  - `cancelled`
  - `failed_to_collect`
- do not resubmit `pending`

`prefect sweep collect` behavior:

- resolve sweep type from the spec path or spec contents
- default to reading the manifest from `infra/ops/manifests/<sweep-id>.submitted.json`
- collect local + remote results
- classify runs as:
  - `completed`
  - `pending`
  - `failed`
  - `cancelled`
  - `failed_to_collect`
  - `not_submitted`

CLI cleanup in this pass:

- remove sweep usage from `prefect run`
- remove old `register experiment-sweep` / `register object-quality-sweep` from docs and public guidance
- keep only the new `prefect sweep ...` commands as the supported sweep surface

### 5. Queue and deployment rules stay purpose-based

Retain current purpose mapping:

- `standard` -> `gpu-fixed`
- `batch` -> `gpu-fixed-batch`
- `debug` -> `gpu-fixed-debug`
- `backfill` -> `gpu-fixed-backfill`

Retain flow-kind deployment names:

- `discoverex-generate-<purpose>`
- `discoverex-verify-<purpose>`
- `discoverex-animate-<purpose>`
- `discoverex-combined-<purpose>`

Allow run-time queue override for isolated submissions via `--work-queue-name`.

### 6. Remove or relocate outdated files

Do a real cleanup, not a documentation-only pass.

- remove obsolete `register` naming from module paths
- remove outdated sweep entrypoint scripts that are replaced by `infra/ops/submitters/*` and `infra/ops/collectors/*`
- update helper scripts like `bin/project` and entry points in `pyproject.toml`
- remove or rewrite docs that still describe branch-scoped registration

If a file is still useful as reference, move it into a clearly named `deprecated/` or `archive/` area under `infra/ops/specs/`, not mixed with live code.

## Test Plan

- import and entry point tests:
  - all old `infra.register.*` references removed
  - `pyproject.toml` console entry points resolve to `infra.ops.*`
- CLI tests:
  - `prefect run gen`
  - `prefect run obj`
  - `prefect sweep run --sweep-spec ...`
  - `prefect sweep run --sweep-spec ... --limit N`
  - `prefect sweep collect --sweep-spec ...`
  - queue override forwarding works
- manifest tests:
  - default manifest path resolves into `infra/ops/manifests/`
  - repeated `sweep run` merges state correctly
  - `--limit N` only selects retry-eligible runs
- collector tests:
  - local case discovery
  - remote artifact recovery
  - Prefect state classification
  - retry-eligible vs pending separation
- deployment tests:
  - purpose-to-queue mapping unchanged
  - deployment registration still produces expected names and queues
- doc sanity:
  - CLI docs and ops docs use only the new `infra/ops` and `prefect sweep` paths

## Assumptions

- This is a hard rename: no long-term `infra/register` shim layer will be kept.
- `prefect run` is reserved for standard one-shot job aliases only.
- `prefect sweep` is the only supported sweep command family after the refactor.
- `infra/ops/manifests/` is the default repo-managed sweep state location.
- Sweep handling should be common across object-quality and naturalness, with submitter/collector selection driven by sweep spec path or contents.

## Decisions Locked During Review

- Sweep execution input is always a sweep spec YAML passed as `--sweep-spec <path>`.
- The sweep spec path is the source of truth for sweep handling in the new CLI surface.
- The refactor SSOT is the object-quality sweep path; other sweep families are treated as legacy in this pass.
- Repeated `sweep run` merges by existing manifest row identity and only overwrites retry-target runtime fields:
  - `flow_run_id`
  - `submitted`
  - `status`
  - optionally `deployment`
  - optionally `updated_at`
- `--limit N` preserves the original job order from the sweep manifest and selects the first `N` retry-eligible rows.
- Existing submitted-manifest files should keep the same contract shape and be relocated under `infra/ops/manifests/`.
