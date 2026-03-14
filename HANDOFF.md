# Handoff

## Current State
- Branch: `feat/engin-worker-observility`
- Latest local commit: `fc68d70` (`WIP`)
- Push status: not pushed
- Push failure: GitHub HTTPS auth missing on this machine

## What Changed
- Deployment registration was moved from local-path registration toward flow-kind-aware remote-source Prefect deployments.
- Default deployment naming rule is now `discoverex-<flow-kind>-<branch-slug>`.
- Default job submission path is now branch-based.
- Worker contract is now aligned around worker-provided `MLFLOW_TRACKING_URI` plus worker-managed engine artifact directory and manifest upload.
- Default job spec is still:
  - `infra/register/job_specs/real-generate-sdxl-gpu-8gb.json`

## Files To Read First
- [HANDOFF.md](/home/esillileu/discoverex/engine/HANDOFF.md)
- [infra/register/branch_deployments.py](/home/esillileu/discoverex/engine/infra/register/branch_deployments.py)
- [infra/register/deploy_prefect_flows.py](/home/esillileu/discoverex/engine/infra/register/deploy_prefect_flows.py)
- [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)
- [infra/register/check_flow_run_status.py](/home/esillileu/discoverex/engine/infra/register/check_flow_run_status.py)
- [infra/register/job_specs/real-generate-sdxl-gpu-8gb.json](/home/esillileu/discoverex/engine/infra/register/job_specs/real-generate-sdxl-gpu-8gb.json)
- [docs/ops/cli.md](/home/esillileu/discoverex/engine/docs/ops/cli.md)

## Current Register Strategy
- `./bin/cli prefect deploy-flow <flow-kind> --branch <branch>`
  - registers a deployment from git source and a flow-kind-specific entrypoint
- `./bin/cli prefect register-flow <flow-kind> --branch <branch>`
  - submits the standard job spec JSON
  - targets deployment `discoverex-<flow-kind>-<branch-slug>`

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
  - `UV_CACHE_DIR="$PWD/.cache/uv" ./bin/cli prefect deploy-flow combined --branch "feat/engin-worker-observility" --work-pool-name gpu-pool`
- Submit current branch standard job:
  - `UV_CACHE_DIR="$PWD/.cache/uv" ./bin/cli prefect register-flow combined --branch "feat/engin-worker-observility"`
- Check flow run status:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run python infra/register/check_flow_run_status.py e45bc516-010a-491f-806b-afd2c8e8ee2c`
