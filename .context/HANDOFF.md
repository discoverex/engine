# HANDOFF (Next Agent)

## 1) Current Snapshot
- Repository root: `/home/esillileu/discoverex/engine`
- Active architecture: hexagonal (`domain` / `application` / `adapters` / `bootstrap`)
- Canonical spec source: `.context/canon.md`
- Current default branch in local workspace: `dev`

## 2) Latest State Applied

### A. Boundary hardening
- `application` use-cases no longer depend directly on `bootstrap`.
- Added application-level context contract:
  - `src/discoverex/application/context.py` (`AppContextLike`)
- Added architecture guard:
  - `tests/test_architecture_constraints.py` now checks `application` does not import `discoverex.bootstrap`.

### B. Dataclass -> Pydantic migration (completed for current dataclass set)
- Migrated:
  - `src/discoverex/models/types.py`
  - `src/discoverex/application/use_cases/gen_verify/types.py`
  - `src/discoverex/bootstrap/context.py`
  - `src/discoverex/adapters/outbound/models/runtime.py`
- Runtime note:
  - `bootstrap/AppContext` uses `BaseModel` with `arbitrary_types_allowed`.
  - Port-holder fields are typed as `Any` to avoid Protocol runtime schema issues.

### C. Artifact consistency + MinIO verification hardening
- Added FX artifact generator:
  - `src/discoverex/adapters/outbound/models/fx_artifact.py`
- Wired FX adapters to ensure output image file exists.
- Fixed verification payload consistency between local saved bundle and report overwrite:
  - `src/discoverex/adapters/outbound/storage/artifact.py`
- Added regression tests:
  - `tests/test_artifact_verification_consistency.py`
  - `tests/test_fx_output_artifact.py`
- Added MinIO E2E verification script:
  - `scripts/check_minio_scene_bundle.py`

### D. Runtime mode documentation (local vs worker)
- Added:
  - `docs/runtime-mode-guide.md`
- Linked/updated:
  - `README.md`
  - `docs/execution-contract.md`
  - `docs/handheld-ops-card.md`

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
- `perception=hf` path is the main real HF inference route.
- `hidden_region/inpaint/fx` HF adapters still include placeholder behavior.
- Infra/ops flow can run now, but full “all stages real-model quality” requires follow-up adapter implementations.

## 5) Validation Status (recent)
- Architecture/type/test checks passed on updated boundaries and DTO migration.
- Pipeline smoke (`gen-verify`) passed in CPU/tiny mode.
- MinIO registration + retrieval + hash consistency verified via:
  - `scripts/check_minio_scene_bundle.py`

## 6) Important Commands
- Full dev dependencies for current flows:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra dev --extra tracking --extra ml-cpu --extra storage`
- Core checks:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev ruff check .`
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev pytest -q`
- MinIO bundle check:
  - `UV_CACHE_DIR="$PWD/.cache/uv" uv run python scripts/check_minio_scene_bundle.py --scene-id <scene_id> --version-id <version_id>`

## 7) Remaining Gaps / Recommended Next Steps
1. Implement non-placeholder HF inference for `hidden_region/inpaint/fx`.
2. Add CI smoke for local mode and worker-mode override set.
3. Add fail-fast worker preflight (required env + adapter override validation).

## 8) Git Convention Reference
- Use `.context/git-conventions.md` (branch naming, empty intro commit, prefix rules, no-ff merge).
