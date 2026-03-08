# Repository Guidelines

## Project Structure & Module Organization
This is a Python engine repository with a hexagonal layout and canonical scene contract.
- Documentation navigation entrypoint is `.context/overview.md` (index only).
- Canonical spec source is `.context/canon.md`.
- `src/discoverex/domain`: canonical DTO/contracts, invariants, domain services
- `src/discoverex/application/ports`: use-case dependencies (model/storage/tracker/io/reporting ports)
- `src/discoverex/application/context.py`: application-layer context contract (`AppContextLike`)
- `src/discoverex/application/use_cases`: orchestration logic (`gen_verify`, `verify_only`, `replay_eval`)
- `src/discoverex/adapters/inbound/cli`: Typer entrypoint (`discoverex`)
- `src/discoverex/adapters/outbound`: concrete adapters (dummy/HF models, storage, MLflow tracking, scene I/O, report writer)
- `src/discoverex/bootstrap`: Hydra `_target_` composition into app context
- `conf/models`, `conf/adapters`, `conf/*.yaml`: composable Hydra config groups
- `orchestrator/`: external scheduler wrapper flows (Prefect)
- `infra/`: local service stack (`docker-compose.yml`)

Removed legacy layers (hard-cut):
- `src/discoverex/pipelines`
- `src/discoverex/cli` (moved to `adapters/inbound/cli`)
- `src/discoverex/generation`
- `src/discoverex/verification`
- `src/discoverex/ux`
- `src/discoverex/storage`
- `src/discoverex/tracking`

Documentation navigation rule:
- Start from `.context/overview.md` to locate relevant docs.
- For architecture/contract decisions, treat `.context/canon.md` as source of truth.
- For current implementation/verification status, use `.context/HANDOFF.md`.

## Build, Test, and Development Commands
- Prefer devcontainer runtime first (`.devcontainer/devcontainer.json`, GPU: `.devcontainer/gpu/devcontainer.json`).
- Devcontainer policy: `remoteUser: vscode`, `updateRemoteUserUID: true`.
- Always use project-local uv cache: `UV_CACHE_DIR="$PWD/.cache/uv"`.
- MLflow is mandatory for pipeline execution; install tracking extra.

Initial setup:
- `mkdir -p .cache/uv`
- `UV_CACHE_DIR="$PWD/.cache/uv" uv venv .venv`
- `UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking --extra dev`

When using MinIO/Postgres adapters:
- `UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra storage`

Recommended wrappers:
- `make init`
- `make sync`
- `make lint`
- `make typecheck`
- `make test`
- `make run ARGS='discoverex generate --background-asset-ref bg://dummy'`

Direct run examples:
- `UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex generate --background-asset-ref <asset>`
- `UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex verify --scene-json <path>`
- `UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex animate --scene-jsons <a> --scene-jsons <b>`

Legacy command shim (`gen-verify`, `verify-only`, `replay-eval`) is still accepted, but emits deprecation warnings.

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` modules/functions, `PascalCase` classes.
- Keep each production file under `src/discoverex` at 200 lines or less.
- Enforce one responsibility per file.
- Use package facades (`__init__.py`) aggressively for encapsulation/stable imports.
- Keep business contracts explicit in `domain/`; adapters must not alter canonical semantics.
- Add integrations via `application/ports` + `adapters/outbound` only.

## Testing Guidelines
- Add tests under `tests/` when introducing logic changes.
- Name tests by behavior (example: `test_verify_only_rejects_missing_scene_json`).
- Validate with:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev ruff check .`
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev mypy src tests`
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev pytest -q`
- Maintain architecture tests for:
  - line-count cap
  - no legacy layer imports
  - use-case boundary constraints

## Commit & Pull Request Guidelines
- Prefer scoped messages: `type(scope): short summary`.
- Keep commits focused to one concern.
- PRs should include purpose, key files changed, commands run, required config/env updates.

## Current Engineering Directives (Conversation Baseline)
- Configuration:
  - Hydra config is single source of truth.
  - Use `oc.env` for environment-derived values, not dotenv loading.
  - Resolve tracking URI via `runtime.env.tracking_uri`.
- Hexagonal boundaries:
  - Use cases depend on application/domain contracts only (no direct bootstrap import).
  - Adapters are the only concrete integration boundary.
- Runtime integration:
  - Transformers/PyTorch logic lives in outbound model adapters (`hf_*`).
  - Keep dummy adapters for local/offline/testing.
  - Current real HF inference path is strongest in `perception`; other HF adapters include placeholder behavior.
- Engine scope:
  - This repo stays execution-engine only.
  - Scheduler/queue/worker orchestration remains external.
  - External scheduler contract uses Hydra override string lists (`docs/execution-contract.md`).
- Dependency policy:
  - Use `uv` as canonical workflow (`uv add`, `uv lock`, `uv sync`).
  - Keep dependencies current and avoid deprecated APIs/packages.

## Runtime Modes
- Local mode: local artifact/meta + `mlflow_file` tracker
- Worker mode: minio/artifact + `mlflow_server` tracker (+ optional postgres metadata)
- See `docs/runtime-mode-guide.md` and `docs/execution-contract.md`.

## Validation Scripts
- MinIO scene bundle verification:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run python scripts/check_minio_scene_bundle.py --scene-id <scene_id> --version-id <version_id>`
