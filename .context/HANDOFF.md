# HANDOFF (Next Agent)

## 1) Current Snapshot
- Repository root: `/home/esillileu/discoverex/engine`
- Active architecture: hexagonal (`domain` / `application` / `adapters` / `bootstrap`)
- Canonical spec source: `.context/canon.md`
- Current default branch in local workspace: `dev`

## 2) Latest State Applied

### A. Prefect migration baseline (v2 + v1 shim)
- Engine command baseline is now `generate | verify | animate`.
- `v1` command shim remains supported:
  - `gen-verify -> generate`
  - `verify-only -> verify`
  - `replay-eval -> animate`
- Legacy shim calls emit deprecation warnings in CLI/launcher paths.

### B. Flow orchestration status
- Entry flow dispatch is in `src/discoverex/flows/engine.py`.
- `generate` and `verify` are now implemented as Prefect stage flows:
  - `src/discoverex/flows/generate.py`
  - `src/discoverex/flows/verify.py`
- `animate` is intentionally kept as stub in this phase.
- Subflow wiring lives in `src/discoverex/flows/subflows.py` and Hydra flow groups.

### C. Error payload normalization
- Entry flow now catches exceptions and returns canonical failure payload:
  - `status=failed`
  - `failure_reason`
  - `metadata.command`, `metadata.error_type`
  - command-specific envelope keys (`scene_json` or `report`) preserved.

### D. Documentation sync (command model)
- Updated docs to v2 baseline + legacy shim warning:
  - `README.md`
  - `docs/runtime-mode-guide.md`
  - `docs/handheld-ops-card.md`
  - `docs/pipeline-adapter-guide.md`
  - `docs/Validator/DIR.md`
  - `docs/execution-contract.md`

## 3) Operational Model (as of now)
- Local mode (default):
  - `adapters/artifact_store=local`
  - `adapters/metadata_store=local_json`
  - `adapters/tracker=mlflow_file`
- Worker mode (recommended):
  - `adapters/artifact_store=minio`
  - `adapters/tracker=mlflow_server`
  - optional `adapters/metadata_store=postgres`

## 4) Model Implementation Reality Check
- `perception=hf` is the strongest real HF inference path.
- `hidden_region/inpaint/fx` HF adapters still contain placeholder behavior.
- Engine orchestration is now Prefect-centered, but model-quality hardening remains.

## 5) Validation Status (recent)
- Passed:
  - `ruff check` on changed flow/contract/docs-adjacent tests
  - `mypy` on flow/contract/CLI modules
  - `pytest` for contract/launcher/register/flows/architecture boundary suites
- Note:
  - Prefect temporary server shutdown may emit a logging handler warning during tests; test results remain green.

## 6) Important Commands
- Setup:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra dev --extra tracking --extra ml-cpu --extra storage`
- Core checks:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev ruff check .`
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev mypy src tests`
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev pytest -q`

## 7) Remaining Gaps / Next Steps
1. Implement real `animate` use case (replace stub).
2. Expand generate/verify subflow granularity only for high-value retry/parallel steps.
3. Add real worker/deployment smoke checks against Prefect deployment target.
4. Keep docs/contracts synced if shim sunset policy is introduced.

## 8) Immediate Follow-up Plan
1. Land current branch into `dev` with split commits (`feat`/`test`/`docs`) per git convention.
2. Add deployment-level smoke workflow for `discoverex generate` + `discoverex verify`.
3. Define shim sunset policy draft (`v1` warning period, cutoff date, fail mode) in `docs/execution-contract.md`.
