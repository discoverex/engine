# Discoverex Core - Project Overview and Handoff

## 1) Product/Architecture Intent (from owner)

### Primary goal
- Build `discoverex-core` engine repository.
- Lock global canonical `Scene` contract as root entity (Region-first, bbox-based).
- Engine scope includes: generation -> verification -> UX(judging/packaging) -> storage/tracking.
- Explicitly exclude training/data-building code.

### Boundaries to keep
- `Scene` owns references to background/regions/goal/answer/verification/difficulty/artifacts.
- Region-first, bbox only for now.
- Keep future slot for mask (`geometry.type`, `mask_ref`) without implementing segmentation logic.
- Verification must be score-centric while preserving signals for analysis/replay/training.
- Orchestrator must stay thin wrapper; business logic must remain inside engine pipelines.
- Prefect now, future Airflow migration should be wrapper-level only.

### Collaboration/ops intent
- Shared services (desktop/CPU): MLflow tracking server + Postgres + MinIO.
- GPU laptop: run compute/inference pipelines.
- Team dev machine: code + analysis + MLflow UI usage.
- Share via central services/storage, not by committing runtime artifacts.

## 2) Current Repository State

Implemented structure (major):
- `src/discoverex/domain`: canonical DTOs (`scene`, `region`, `goal`, `verification`)
- `src/discoverex/models`: function+handle inference API
- `src/discoverex/generation`: candidate/inpaint/compose
- `src/discoverex/verification`: logical/perception/integration
- `src/discoverex/ux`: judge/packaging
- `src/discoverex/pipelines`: `gen_verify`, `verify_only`, `replay_eval`
- `src/discoverex/storage`: local + minio artifact store; local json + postgres metadata store
- `src/discoverex/tracking`: MLflow tracker wrapper
- `src/discoverex/cli`: Typer CLI
- `orchestrator/prefect_flows.py`: Prefect thin wrapper flows
- `conf/*.yaml`: Hydra configs per pipeline
- `infra/docker-compose.yml`: postgres/minio/mlflow (+ optional airflow profile)
- `.devcontainer/`: default + gpu configs
- `.env.example`: central env var template

Packaging/runtime:
- Python 3.11+
- `uv` project with dependencies: pydantic/mlflow/prefect/typer/hydra/boto3/sqlalchemy/psycopg

## 3) Key Implementation Decisions Applied

1. CLI standard: **Typer**
- Commands:
  - `discoverex gen-verify`
  - `discoverex verify-only`
  - `discoverex replay-eval`
- Output is JSON-like single-line payload for automation friendliness.

2. Model API standard: **function + handle**
- Each model module exposes:
  - `load(model_ref_or_version) -> ModelHandle`
  - `predict(handle, inputs) -> outputs`

3. Hydra scope: **experiment/pipeline config layer only**
- CLI stays Typer.
- Hydra loads config from `conf/*.yaml` and supports `-o key=value` overrides.

4. Prefect scope: **orchestrator-only features**
- Retries/scheduling/worker orchestration in `orchestrator/`.
- Core engine pipeline modules do not import Prefect.

5. Storage strategy
- Artifact store:
  - `LocalArtifactStore`
  - `MinioArtifactStore` (S3-compatible)
- Metadata store:
  - `LocalMetadataStore` (JSON index)
  - `PostgresMetadataStore`

## 4) Verified Execution Status

### Local mode verification
- `uv sync` succeeded.
- `gen_verify` succeeded.
- `verify_only` succeeded.
- `replay_eval` succeeded.
- Artifacts and MLflow local/file tracking produced as expected.

### Central services verification (docker compose)
Services started and validated:
- Postgres at `127.0.0.1:5432`
- MinIO at `127.0.0.1:9000` (console 9001)
- MLflow at `127.0.0.1:5000`

Central-backend pipeline runs validated:
- `gen_verify` with overrides for minio/postgres/mlflow-server succeeded.
- `verify_only` succeeded.
- `replay_eval` succeeded.

Evidence validated:
- Postgres `scene_metadata` rows inserted/updated.
- MinIO objects present for scene bundle and mlflow artifacts.
- MLflow run params/metrics/artifacts visible and artifact URI points to `s3://discoverex-artifacts/...`.

### Prefect server/worker/deployment verification
Validated flow lifecycle through persistent server model:
1. Started Prefect server (`127.0.0.1:4200`)
2. Created work pool `discoverex-process`
3. Started worker on that pool
4. Created deployment for `gen_verify_flow`
5. Triggered deployment run with watched completion
6. Added interval schedule (5 minutes) and confirmed schedule listing

Observed and resolved issue:
- Initial deployment run failed with `NoCredentialsError` (MLflow artifact upload from worker process).
- Root cause: worker process env lacked AWS credentials.
- Fix: start worker with required env (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `MLFLOW_S3_ENDPOINT_URL`).
- Re-run completed successfully.

## 5) Important Technical Notes for Next Operator

1. MinIO compatibility fix
- `MinioArtifactStore` was patched to avoid intermittent checksum mismatch (`XAmzContentSHA256Mismatch`) by:
  - explicit `botocore.config.Config` for s3v4/path-style/checksum behavior
  - using `put_object` with bytes for scene bundle upload

2. Worker environment requirements
- For Prefect deployment runs that log to MLflow S3 artifacts, worker process must include:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `MLFLOW_S3_ENDPOINT_URL`
- Otherwise flow may fail at artifact logging phase even if pipeline logic is otherwise correct.

3. MLflow local file backend warning
- MLflow emits deprecation warning for filesystem backend in 2026.
- Prefer central server mode (already scaffolded/validated).

4. Existing external containers
- Host environment may contain unrelated running containers from other projects.
- Current compose operates with `infra/docker-compose.yml` service names prefixed around discoverex services.

## 6) Devcontainer Validation Status

Validated:
- `.devcontainer/devcontainer.json` parses and includes `postCreateCommand`.
- Base image run test succeeded:
  - uv install works
  - `uv sync --frozen` works against mounted project

GPU config validation:
- `.devcontainer/devcontainer.gpu.json` parses and bootstrap steps run in `nvidia/cuda` image.
- On non-GPU host, container warns driver not detected (expected).
- GPU runtime behavior itself must be validated on actual GPU-capable machine.

## 7) Commands Used Frequently (handoff quick refs)

Central services:
```bash
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs mlflow --tail=120
```

Typer + Hydra pipeline runs (central backend example):
```bash
MLFLOW_S3_ENDPOINT_URL=http://127.0.0.1:9000 \
AWS_ACCESS_KEY_ID=minioadmin \
AWS_SECRET_ACCESS_KEY=minioadmin \
uv run discoverex gen-verify \
  --background-asset-ref demo/backgrounds/bg.png \
  -o storage.artifact_backend=minio \
  -o storage.metadata_backend=postgres \
  -o storage.metadata_db_url=postgresql+psycopg://discoverex:discoverex@127.0.0.1:5432/discoverex \
  -o storage.artifact_bucket=discoverex-artifacts \
  -o storage.s3_endpoint_url=http://127.0.0.1:9000 \
  -o tracking.tracking_uri=http://127.0.0.1:5000
```

Prefect server/worker/deployment:
```bash
uv run prefect config set PREFECT_API_URL=http://127.0.0.1:4200/api
uv run prefect server start --host 127.0.0.1 --port 4200
uv run prefect work-pool create discoverex-process -t process
PREFECT_API_URL=http://127.0.0.1:4200/api \
MLFLOW_S3_ENDPOINT_URL=http://127.0.0.1:9000 \
AWS_ACCESS_KEY_ID=minioadmin \
AWS_SECRET_ACCESS_KEY=minioadmin \
uv run prefect worker start --pool discoverex-process
```

## 8) Open Items / Suggested Next Steps

- Add automated tests for:
  - storage backend switching
  - Prefect deployment execution path with env propagation
  - Postgres schema migration/versioning strategy
- Add `prefect.yaml` project config for cleaner deployment UX.
- Decide policy for flow failure when tracking upload fails (strict fail vs soft-fail).
- Add CI checks for CLI smoke tests and config schema validation.

---
This file is intended as the single handoff context for the next operator.

## 9) Git Convention Reference
- See `.context/git-conventions.md` for branch naming, empty-commit initialization, commit prefixes, and merge rules.
