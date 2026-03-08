# 런타임 모드 운영 가이드 (로컬/워커)

## 목적
- 동일 엔진(`discoverex`)을 환경별로 일관되게 운영합니다.
- 로컬은 로컬 경로/로컬 추적을 사용하고, 워커는 워커 인프라(MinIO/MLflow/Postgres 등)를 사용합니다.

## 핵심 개념
- 실행 엔진은 동일: `discoverex generate|verify|animate`
- 차이는 Hydra adapter 선택과 runtime env 주입입니다.
- 오케스트레이터 워커에서는 `python -m discoverex.orchestrator_contract.launcher`를
  `entrypoint`로 호출하고, 실제 CLI 인자는 `ORCH_JOB_INPUTS_JSON`으로 전달합니다.
- 결과 전달 단위:
  - CLI stdout JSON (`scene_json` 또는 `report`)
  - artifacts 저장소
  - tracker 기록

## 모드 정의

### Local Mode (기본)
- `adapters/artifact_store=local`
- `adapters/metadata_store=local_json`
- `adapters/tracker=mlflow_file`
- 기본 추적 URI: `runtime.env.tracking_uri=sqlite:///mlflow.db`

의도:
- 개발/디버깅/로컬 스모크 실행
- 로컬 파일 시스템 기반 산출물 확인

### Worker Mode (권장)
- `adapters/artifact_store=minio`
- `adapters/tracker=mlflow_server`
- `adapters/metadata_store=postgres` (선택)
- 워커 환경변수:
  - `MLFLOW_TRACKING_URI`
  - `MLFLOW_S3_ENDPOINT_URL`
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `METADATA_DB_URL` (postgres 사용 시)

의도:
- 외부 워커/스케줄러 환경에서 중앙 추적/저장소 사용

## 모드별 실행 예시

### 1) Local Mode
```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex generate \
  --background-asset-ref bg://dummy \
  -o runtime/model_runtime=cpu \
  -o models/hidden_region=tiny_torch \
  -o models/inpaint=tiny_torch \
  -o models/perception=tiny_torch \
  -o models/fx=tiny_torch
```

### 2) Worker Mode
```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex generate \
  --background-asset-ref bg://dummy \
  -o adapters/artifact_store=minio \
  -o adapters/tracker=mlflow_server \
  -o adapters/metadata_store=postgres \
  -o runtime/model_runtime=cpu \
  -o models/perception=hf
```

`verify`, `animate`도 동일하게 adapter/runtime override 패턴을 적용합니다.

레거시 명령(`gen-verify`, `verify-only`, `replay-eval`)은 현재 shim으로 동작하지만,
실행 시 deprecation 경고가 출력됩니다.

## 운영 가드레일
- 워커 payload 템플릿에 adapter override를 고정합니다.
- 워커 실행 직전 필수 env 누락 여부를 검사하고, 누락 시 fail-fast 처리합니다.
- 워커에서 `local` 저장소/트래커 adapter 사용을 금지합니다.

권장 워커 override 최소 세트:
- `adapters/artifact_store=minio`
- `adapters/tracker=mlflow_server`
- 필요 시 `adapters/metadata_store=postgres`

## 산출물/추적 위치 매핑

| 항목 | Local Mode | Worker Mode |
|---|---|---|
| Scene 산출물 | `artifacts/scenes/...` | MinIO bucket (`scenes/...`) |
| Replay report | `artifacts/reports/...` | 워커 스토리지 정책에 따름(기본 로컬 + tracker artifact) |
| Tracker | `mlflow_file` (로컬 URI) | `mlflow_server` (원격 URI) |
| Metadata | `local_json` | `postgres`(선택) |

## 트러블슈팅
- 워커인데 로컬 artifacts에 저장됨:
  - `adapters/artifact_store=minio` override 누락 여부 확인
- MLflow run이 생성되지 않음:
  - `adapters/tracker=mlflow_server` 및 `MLFLOW_TRACKING_URI` 확인
- MinIO 업로드 실패:
  - `MLFLOW_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` 확인
- Postgres metadata 실패:
  - `METADATA_DB_URL` 확인

## 검증 루틴
1. 로컬 모드 기본 실행 1회
2. 워커 모드 override로 실행 1회
3. MinIO 등록 검증 스크립트 실행

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run python scripts/check_minio_scene_bundle.py \
  --scene-id <scene_id> \
  --version-id <version_id>
```

## 관련 문서
- `docs/execution-contract.md`
- `docs/handheld-ops-card.md`
- `docs/pipeline-adapter-guide.md`
