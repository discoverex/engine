# discoverex-core

Discoverex Core 엔진 레포입니다. Scene Canonical(Region-first, bbox) 계약을 중심으로,
Hydra 기반 어댑터 조립으로 `gen-verify`, `verify-only`, `replay-eval` 파이프라인을 실행합니다.

## 핵심 원칙
- Scene이 루트 엔티티입니다.
- Application use case는 port 인터페이스에만 의존합니다.
- 외부 연동은 `adapters/outbound`에서만 구현합니다.
- 실행 진입점은 `adapters/inbound/cli`입니다.
- 모든 파이프라인 실행에는 MLflow tracker가 필수입니다.

## 프로젝트 구조
- `src/discoverex/domain`: 캐논 DTO, 불변식, 도메인 서비스
- `src/discoverex/application/ports`: 모델/스토리지/트래킹/IO/리포팅 포트
- `src/discoverex/application/use_cases`: `gen_verify`, `verify_only`, `replay_eval`
- `src/discoverex/adapters/inbound/cli`: Typer CLI 진입점
- `src/discoverex/adapters/outbound`: 모델/스토리지/트래커/Scene IO/리포트 어댑터
- `src/discoverex/bootstrap`: Hydra config 기반 조립(Composition Root)
- `conf/models`, `conf/adapters`, `conf/*.yaml`: Hydra 설정 그룹
- `orchestrator/`: 외부 스케줄러 연동 래퍼(Prefect)

## 최초 설치 (로컬/Devcontainer 공통)
`uv` 실행은 항상 프로젝트 내부 캐시를 사용합니다.

```bash
mkdir -p .cache/uv
UV_CACHE_DIR="$PWD/.cache/uv" uv venv .venv
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking
```

개발 검증까지 함께 설치하려면:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking --extra dev
```

## Devcontainer
- 기본: `.devcontainer/devcontainer.json`
- GPU: `.devcontainer/gpu/devcontainer.json`
- 공통 정책: `remoteUser: vscode`, `updateRemoteUserUID: true`

기동 예시:

```bash
devcontainer up --workspace-folder /home/esillileu/discoverex/engine --config /home/esillileu/discoverex/engine/.devcontainer/devcontainer.json
```

## 실행 방법
### `make` 사용 (권장)

```bash
make sync
make run ARGS='discoverex gen-verify --background-asset-ref bg://dummy'
make run ARGS='discoverex verify-only --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json'
make run ARGS='discoverex replay-eval --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json'
```

### `uv` 직접 실행

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex gen-verify --background-asset-ref bg://dummy
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex verify-only --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex replay-eval --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json
```

## 품질 검증

```bash
make lint
make typecheck
make test
```

또는

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev ruff check .
UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev mypy src tests
UV_CACHE_DIR="$PWD/.cache/uv" uv run --extra dev pytest -q
```

## 파이프라인 구성요소 추가 방법
새 모델/스토리지/트래커/IO를 설정만으로 교체 가능하게 만들려면 아래 순서를 따릅니다.

1. 포트 확인
- 모델: `src/discoverex/application/ports/models.py`
- 스토리지: `src/discoverex/application/ports/storage.py`
- 트래커: `src/discoverex/application/ports/tracking.py`
- Scene IO: `src/discoverex/application/ports/io.py`
- 리포트: `src/discoverex/application/ports/reporting.py`

2. 어댑터 구현
- 위치: `src/discoverex/adapters/outbound/<group>/my_adapter.py`
- 규칙: use case에서 concrete adapter를 직접 import하지 않음

3. Hydra 설정 등록
- 파일: `conf/<models|adapters>/<group>/my_adapter.yaml`

예시:

```yaml
# @package adapters.tracker
_target_: discoverex.adapters.outbound.tracking.my_adapter.MyTrackerAdapter
```

4. 설정 선택
- `conf/gen_verify.yaml`, `conf/verify_only.yaml`, `conf/replay_eval.yaml` 기본값에 추가하거나
- 실행 시 `-o` override로 선택

## MLflow 필수 정책
모든 파이프라인은 tracker를 통해 실행 기록을 남깁니다.
기본 tracker는 `adapters/tracker=mlflow_file`이며, 실행 전 `--extra tracking` 설치가 필요합니다.

## 참고 문서
- `docs/pipeline-adapter-guide.md`
- `docs/handheld-ops-card.md`
- `docs/execution-contract.md`
