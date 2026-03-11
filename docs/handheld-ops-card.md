# Discoverex 운영 카드

## 저장소 목적

Discoverex는 캐논 중심 퍼즐 엔진이며 헥사고널 아키텍처로 구성됩니다.

- `domain`: Scene 캐논 DTO/불변식/도메인 서비스
- `application/ports`: 모델/스토리지/트래킹/Scene IO/리포팅 인터페이스
- `application/use_cases`: 파이프라인 오케스트레이션
- `adapters/inbound/cli`: CLI 진입점
- `adapters/outbound`: 외부 연동 구현체
- `bootstrap`: 설정 기반 의존성 조립 (`build_context`)

캐논 원문은 `.context/canon.md`, 런타임 모델은 `src/discoverex/domain/*`가 담당합니다.

## 파이프라인 I/O
레거시 명령(`gen-verify`, `verify-only`, `replay-eval`)은 shim으로 지원되지만 deprecation 경고가 출력됩니다.

### 1) `generate`
입력:
- `--background-asset-ref <asset_ref>`
- 선택: `--config-name <config_name>`, `--config-dir <config_dir>`, `-o <hydra_override>`

출력(stdout JSON):
- `scene_id`, `version_id`, `status`, `scene_json`, `execution_config`

아티팩트:
- `{artifacts_root}/scenes/{scene_id}/{version_id}/scene.json`
- `{artifacts_root}/scenes/{scene_id}/{version_id}/verification.json`
- `{artifacts_root}/scenes/{scene_id}/{version_id}/composite.png`

### 2) `verify`
입력:
- `--scene-json <path_to_scene_json>`
- 선택: `--config-name <config_name>`, `--config-dir <config_dir>`, `-o <hydra_override>`

출력(stdout JSON):
- `scene_id`, `version_id`, `status`, `scene_json`, `execution_config`

### 3) `animate` (현재 stub)
입력:
- `--scene-jsons <scene1.json> --scene-jsons <scene2.json> ...`
- 선택: `--config-name <config_name>`, `--config-dir <config_dir>`, `-o <hydra_override>`

출력(stdout JSON):
- `report` 또는 실패 payload, `execution_config`

아티팩트:
- `{artifacts_root}/reports/replay_eval_<timestamp>.json`

## 필수 실행 정책
- 모든 파이프라인은 MLflow tracker를 반드시 사용합니다.
- 실행 전 `tracking` extra 설치가 필요합니다.

```bash
mkdir -p .cache/uv
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking
```

## 운영 모드 (로컬/워커)
- 로컬 모드(기본): `artifact_store=local`, `metadata_store=local_json`, `tracker=mlflow_file`
- 워커 모드(권장): `artifact_store=minio`, `tracker=mlflow_server`, 필요 시 `metadata_store=postgres`
- 워커 입력 env: `MLFLOW_TRACKING_URI`
- 워커 프록시 env: `MLFLOW_TRACKING_PROXY_URL`
- child engine env: `MLFLOW_TRACKING_URI`(프록시 URL), `MLFLOW_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (및 `METADATA_DB_URL`)
- 상세 절차: `docs/runtime-mode-guide.md`

## 최소 실행 절차

```bash
make sync
make run ARGS='discoverex generate --config-name generate --config-dir conf --background-asset-ref bg://dummy'
make run ARGS='discoverex verify --config-name verify --config-dir conf --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json'
make run ARGS='discoverex animate --config-name animate --config-dir conf --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json'
```

직접 실행 예시:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex generate \
  --config-name generate \
  --config-dir conf \
  --background-asset-ref bg://dummy
```

```bash
python scripts/register_prefect_job.py \
  --command generate \
  --config-name generate \
  --repo-url https://github.com/<org>/discoverex-engine.git \
  --ref main \
  --background-asset-ref bg://dummy
```

## 설정으로 바꿀 수 있는 항목
- 모델: `models/hidden_region`, `models/inpaint`, `models/perception`, `models/fx`
- 어댑터: `adapters/artifact_store`, `adapters/metadata_store`, `adapters/tracker`, `adapters/scene_io`, `adapters/report_writer`
- 런타임 파라미터: `runtime`, `thresholds`, `model_versions`
- 설정 파일 선택: `--config-name`, `--config-dir`

주의:
- 새로운 파이프라인 타입 추가는 use case/CLI 코드 추가가 필요합니다.

## Prefect 식별 규칙
- flow 이름은 고정입니다.
- config별 구분은 deployment/job 이름으로 합니다.
- 기본 규칙:
  - deployment: `discoverex-<command>--<config_name>`
  - job/run name: `<command>--<config_name>--<execution_profile>`

## 실행 설정 기록
- 모든 실행은 `resolved_execution_config.json`을 생성합니다.
- 기본 위치:
  - `artifacts/execution/<command>/<run_id>/resolved_execution_config.json`
- `MLflow`에는 검색용 params와 함께 이 파일이 artifact로 기록됩니다.
- 민감값은 redaction 처리됩니다.
- worker 전용 인증 env는 child engine snapshot에 남지 않습니다.

## 숨은그림찾기 전달 규칙
- 엔진 결과 `scene.json`을 delivery 번들로 변환해 서버에 전달합니다.
- 변환 패키지: `delivery/spot_the_hidden` (메인 패키지 외부)
- 번들 파일: `artifacts/scenes/<scene_id>/<version_id>/delivery/spot_hidden_bundle.json`
- 번들 내부에는 `playable` + `answer_key`가 같이 들어갑니다.
- 프런트 응답에는 `answer_key`를 제거하고 `playable`만 전달합니다.
- 이미지는 바이너리 인라인이 아닌 `image_ref` 참조 방식으로 전달합니다.

## 빠른 트러블슈팅
- Hydra target import 에러:
  - `conf/models/*`, `conf/adapters/*`의 `_target_` 경로 확인
- Tracker 초기화 에러:
  - `uv sync --extra tracking` 실행 여부 확인
- Postgres metadata 어댑터 에러:
  - `METADATA_DB_URL` 확인
- MinIO 업로드 에러:
  - `MLFLOW_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` 확인

## 주요 파일
- CLI: `src/discoverex/adapters/inbound/cli/main.py`
- Bootstrap: `src/discoverex/bootstrap/factory.py`
- Use cases: `src/discoverex/application/use_cases/`
- Ports: `src/discoverex/application/ports/`
- 캐논: `.context/canon.md`, `src/discoverex/domain/`
- 설정: `conf/models/`, `conf/adapters/`, `conf/*.yaml`
