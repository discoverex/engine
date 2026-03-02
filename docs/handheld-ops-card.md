# Discoverex 운영 카드

## 저장소 목적

Discoverex는 캐논 중심 퍼즐 엔진이며 헥사고널 아키텍처로 구성됩니다.

- `domain`: Scene 캐논 DTO/불변식/도메인 서비스
- `application/ports`: 모델/스토리지/트래킹/Scene IO/리포팅 인터페이스
- `application/use_cases`: 파이프라인 오케스트레이션
- `adapters/inbound/cli`: CLI 진입점
- `adapters/outbound`: 외부 연동 구현체
- `bootstrap`: 설정 기반 의존성 조립 (`build_context`)

캐논 원문은 `canon.md`, 런타임 모델은 `src/discoverex/domain/*`가 담당합니다.

## 파이프라인 I/O

### 1) `gen-verify`
입력:
- `--background-asset-ref <asset_ref>`

출력(stdout JSON):
- `scene_id`, `version_id`, `status`, `scene_json`

아티팩트:
- `{artifacts_root}/scenes/{scene_id}/{version_id}/scene.json`
- `{artifacts_root}/scenes/{scene_id}/{version_id}/verification.json`
- `{artifacts_root}/scenes/{scene_id}/{version_id}/composite.png`

### 2) `verify-only`
입력:
- `--scene-json <path_to_scene_json>`

출력(stdout JSON):
- `scene_id`, `version_id`, `status`, `scene_json`

### 3) `replay-eval`
입력:
- `--scene-jsons <scene1.json> --scene-jsons <scene2.json> ...`

출력(stdout JSON):
- `report`

아티팩트:
- `{artifacts_root}/reports/replay_eval_<timestamp>.json`

## 필수 실행 정책
- 모든 파이프라인은 MLflow tracker를 반드시 사용합니다.
- 실행 전 `tracking` extra 설치가 필요합니다.

```bash
mkdir -p .cache/uv
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking
```

## 최소 실행 절차

```bash
make sync
make run ARGS='discoverex gen-verify --background-asset-ref bg://dummy'
make run ARGS='discoverex verify-only --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json'
make run ARGS='discoverex replay-eval --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json'
```

## 설정으로 바꿀 수 있는 항목
- 모델: `models/hidden_region`, `models/inpaint`, `models/perception`, `models/fx`
- 어댑터: `adapters/artifact_store`, `adapters/metadata_store`, `adapters/tracker`, `adapters/scene_io`, `adapters/report_writer`
- 런타임 파라미터: `runtime`, `thresholds`, `model_versions`

주의:
- 새로운 파이프라인 타입 추가는 use case/CLI 코드 추가가 필요합니다.

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
- 캐논: `canon.md`, `src/discoverex/domain/`
- 설정: `conf/models/`, `conf/adapters/`, `conf/*.yaml`
