# HANDOFF (Next Agent)

## 1) Current Snapshot
- Repository root: `/home/esillileu/discoverex/engine`
- Architecture is now hard-cut hexagonal shape (legacy compatibility layers removed).
- Working tree is dirty and includes unrelated pre-existing edits; confirm commit scope carefully.

## 2) What Is Updated To Latest

### A. Hexagonal hard-cut applied
- Removed legacy layers/directories:
  - `src/discoverex/pipelines`
  - `src/discoverex/cli`
  - `src/discoverex/generation`
  - `src/discoverex/verification`
  - `src/discoverex/ux`
  - `src/discoverex/storage`
  - `src/discoverex/tracking`
- CLI entrypoint moved to inbound adapter:
  - `src/discoverex/adapters/inbound/cli/main.py`
- Script entrypoint updated:
  - `pyproject.toml` → `discoverex = "discoverex.adapters.inbound.cli.main:app"`

### B. Domain service consolidation
- Added domain services package:
  - `src/discoverex/domain/services/__init__.py`
  - `src/discoverex/domain/services/verification.py`
  - `src/discoverex/domain/services/judgement.py`
- Use-cases now consume domain service functions instead of removed `verification/ux` modules:
  - `src/discoverex/application/use_cases/gen_verify/verification_pipeline.py`
  - `src/discoverex/application/use_cases/verify_only.py`

### C. Inbound/outbound wiring updates
- `main.py` now imports CLI app from inbound adapter path.
- `orchestrator/prefect_flows.py` now calls `application/use_cases` + `build_context`, no pipelines wrapper dependency.

### D. Architecture tests updated
- `tests/test_architecture_constraints.py` now asserts:
  - no imports from removed legacy packages
  - removed legacy directories do not exist
  - existing boundary checks remain active
- `tests/test_hexagonal_boundaries.py` target paths updated to current use-case modules.

### E. Runtime/ops docs updated
- `README.md` rewritten for current state:
  - first-time setup
  - make/uv execution
  - pipeline extension flow (port → adapter → Hydra config)
  - MLflow mandatory policy
- `docs/handheld-ops-card.md` CLI entry path corrected.

### F. Build command policy aligned with MLflow mandatory
- `Makefile` updated:
  - `make init` installs `--extra tracking --extra dev`
  - `make sync` installs `--extra tracking`

## 3) Validation Results (latest in this session)
- `make lint` passed.
- `make typecheck` passed.
- `make test` passed.
- Pipeline execution smoke passed after installing tracking extra:
  - `discoverex gen-verify --background-asset-ref bg://dummy`
  - `discoverex verify-only --scene-json <generated_scene_json>`
  - `discoverex replay-eval --scene-jsons <generated_scene_json>`
- MLflow artifact store was created (`mlruns/` present).

## 4) Critical Operational Notes
1. MLflow is required for all pipeline runs in current policy.
   - Ensure dependencies include tracking extra.
2. Use project-local uv cache always:
   - `UV_CACHE_DIR="$PWD/.cache/uv"`
3. Prefer make wrappers to avoid command drift:
   - `make init`, `make sync`, `make lint`, `make typecheck`, `make test`.

## 5) Risks / Re-check Items
1. Because legacy modules were hard-removed, any external code importing old paths will break.
2. Dirty worktree includes broad historical changes; do not assume this handoff-only delta is isolated.
3. Devcontainer CLI `exec` behavior can differ by host permissions; if needed, use `docker exec` directly into the running container.

## 6) Recommended Next Steps
1. If external consumers exist, publish a migration note mapping old imports to new paths.
2. Add a small regression test that runs CLI commands end-to-end in CI (with tracking extra).
3. Consider adding import-linter rules for inbound/application/domain boundary enforcement.

## 7) Useful Commands
- Status: `git status --short`
- Full quality gate:
  - `make lint`
  - `make typecheck`
  - `make test`
- Pipeline smoke:
  - `make run ARGS='discoverex gen-verify --background-asset-ref bg://dummy'`
  - `make run ARGS='discoverex verify-only --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json'`
  - `make run ARGS='discoverex replay-eval --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json'`
