# Handoff

## Current State (2026-03-15)
- Branch: `feat/engin-worker-observility`
- Status: **Stable & Verified**
- Key Achievement: Successfully ran a full generation pipeline on 8GB VRAM with real-time log streaming.

## What Changed
- **OOM Fix (8GB VRAM):** Implemented sequential model loading/unloading. Models no longer reside in memory simultaneously.
- **Hierarchical Logging:** Implemented "Quiet Success, Loud Failure". Detailed logs are streamed at `DEBUG` level, while failures flush `stderr` to `ERROR` level for visibility.
- **YAML Migration:** All job specs migrated to YAML. All tools (`register flow`, `submit-spec`) now use YAML as the primary format.
- **Subflow Linkage:** Engine subprocesses are now linked as **Subflows** in Prefect UI using `PREFECT_PARENT_FLOW_RUN_ID`.
- **Explicit Tasks:** Decomposed `combined` flow into explicit `engine-generate-task` and `engine-verify-task` components.

## Files To Read First
- [REFACTOR_PLAN.md](/home/esillileu/discoverex/engine/REFACTOR_PLAN.md) - Final Status Summary.
- [infra/prefect/dispatch.py](/home/esillileu/discoverex/engine/infra/prefect/dispatch.py) - Logging and subprocess logic.
- [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py) - Explicit task definitions.
- [src/discoverex/application/use_cases/gen_verify/orchestrator.py](/home/esillileu/discoverex/engine/src/discoverex/application/use_cases/gen_verify/orchestrator.py) - Sequential loading logic.

## Current Register Strategy
- `./bin/cli prefect deploy flow <flow-kind> --branch <branch>`
- `./bin/cli prefect register flow <flow-kind> --branch <branch>`
  - targets deployment `discoverex-<flow-kind>-<branch-slug>`
  - uses YAML specs from `infra/register/job_specs/`

## Current Worker Strategy
- Deployment source is remote git, not a machine-local working directory
- Deployment entrypoint points to flow-kind-specific repo-root callables:
  - `prefect_flow.py:run_generate_job_flow`
  - `prefect_flow.py:run_verify_job_flow`
  - `prefect_flow.py:run_animate_job_flow`
  - `prefect_flow.py:run_combined_job_flow`
- Worker bootstrap still happens inside the engine flow runtime after source checkout

## Current Problem
- Remote-source registration is now aligned, but the worker-side execution contract still needs full validation against the orchestrator runtime.

## Error Report
- Deployment:
  - `discoverex-combined-feat-engin-worker-observility`
- Deployment id:
  - `7cc08193-e462-4583-b299-bf21d4d33e3e`
- Latest failed flow run id:
  - `e45bc516-010a-491f-806b-afd2c8e8ee2c`
- State:
  - `Crashed`
- State message:
  - `Flow run process exited with non-zero status code 1.`
- Failure point:
  - `prefect.deployments.steps.set_working_directory`
- Error:
  - `FileNotFoundError: [Errno 2] No such file or directory: '/home/esillileu/discoverex/engine'`

## Root Cause
- The older deployment model assumed a machine-local source path.
- The current refactor replaces that assumption with `flow.from_source(...)`, but runtime behavior against the real worker has not yet been re-verified.

## Why Previous Attempt Failed
- Earlier YAML included:
  - `git_clone`
  - `run_shell_script` with `uv sync`
- That version failed for two separate reasons:
  - remote worker could not clone branch `feat/engin-worker-observility` from GitHub
  - `run_shell_script` was not shaped correctly for Prefect and failed on `cd`
- Those steps were then removed completely.

## What Needs To Be Fixed
- Choose one deployment code-loading strategy and make it consistent.
- Valid options:
  - restore a correct remote code retrieval strategy
  - or make the worker environment permanently host this repo at a known stable path
- Current code assumes the second option, but the actual worker environment does not satisfy it.

## Recommended Fix Direction
- Keep the `flow.from_source(...)` registration path.
- Re-run deployment and worker smoke tests against the real Prefect pool.
- Validate that repo checkout, import-time flow loading, and runtime bootstrap all succeed under the worker image.

## Important Notes
- The repo now exposes flow-kind-specific Prefect entrypoints at repo root.
- The repo contains many unrelated staged-and-committed content migrations and doc moves.
- Do not assume this branch only contains deployment work.

## Useful Commands
- Current branch:
  - `git branch --show-current`
- Re-register current branch deployment:
  - `UV_CACHE_DIR="$PWD/.cache/uv" ./bin/cli prefect deploy flow combined --branch "feat/engin-worker-observility" --work-pool-name gpu-pool`
- Submit current branch standard job:
  - `UV_CACHE_DIR="$PWD/.cache/uv" ./bin/cli prefect register flow combined --branch "feat/engin-worker-observility"`
- Check flow run status:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run python infra/register/check_flow_run_status.py e45bc516-010a-491f-806b-afd2c8e8ee2c`
