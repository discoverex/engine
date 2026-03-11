# discoverex-core

Discoverex Core 엔진 레포입니다. Scene Canonical(Region-first, bbox) 계약을 중심으로,
Hydra 기반 어댑터 조립으로 `generate`, `verify`, `animate` 파이프라인을 실행합니다.
캐논 원문 기준은 `.context/canon.md`입니다.

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
- `delivery/spot_the_hidden`: 숨은그림찾기 배포 번들 스키마/변환(메인 패키지 외부)

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
make run ARGS='discoverex generate --background-asset-ref bg://dummy'
make run ARGS='discoverex verify --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json'
make run ARGS='discoverex animate --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json'
```

### `uv` 직접 실행

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex generate --background-asset-ref bg://dummy
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex verify --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex animate --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json
```

CPU 320x240 실생성(FX tiny SD) 예시:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex generate \
  --background-asset-ref bg://dummy \
  -o models/fx=tiny_sd_cpu \
  -o runtime/model_runtime=cpu \
  -o runtime.width=320 \
  -o runtime.height=240
```

CPU fast 공통 프리셋(`profile=cpu_fast`) 예시:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex generate \
  --background-asset-ref bg://dummy \
  -o profile=cpu_fast

UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex verify \
  --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json \
  -o profile=cpu_fast

UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex animate \
  --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json \
  -o profile=cpu_fast
```

### 오케스트레이터 워커 엔트리포인트

오케스트레이터 JobSpec의 `entrypoint`는 아래 런처를 권장합니다.

```bash
python -m discoverex.orchestrator_contract.launcher
```

런처는 `ORCH_JOB_INPUTS_JSON`을 `OrchestratorInputs`(v1/v2)으로 검증한 뒤
`discoverex generate|verify|animate`을 실행합니다.

레거시 명령(`gen-verify`, `verify-only`, `replay-eval`)은 shim으로 지원되지만
실행 시 deprecation 경고가 출력됩니다.

실제 잡 등록은 아래 스크립트를 사용합니다.

```bash
python register/register_orchestrator_job.py --dry-run --command generate \
  --repo-url https://github.com/<org>/discoverex-engine.git \
  --ref main \
  --background-asset-ref bg://dummy
```

### 운영 모드 분리 (로컬/워커)

- 로컬 개발은 기본 설정(`local` artifact/meta + `mlflow_file`)을 사용합니다.
- 외부 워커는 실행 시 override로 `minio`/`mlflow_server`/`postgres` 조합을 강제합니다.
- 상세 운영 가이드는 `docs/runtime-mode-guide.md`를 참고하세요.

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

### 1. 포트 확인

- 모델: `src/discoverex/application/ports/models.py`
- 스토리지: `src/discoverex/application/ports/storage.py`
- 트래커: `src/discoverex/application/ports/tracking.py`
- Scene IO: `src/discoverex/application/ports/io.py`
- 리포트: `src/discoverex/application/ports/reporting.py`

### 2. 어댑터 구현

- 위치: `src/discoverex/adapters/outbound/<group>/my_adapter.py`
- 규칙: use case에서 concrete adapter를 직접 import하지 않음

### 3. Hydra 설정 등록

- 파일: `conf/<models|adapters>/<group>/my_adapter.yaml`

예시:

```yaml
# @package adapters.tracker
_target_: discoverex.adapters.outbound.tracking.my_adapter.MyTrackerAdapter
```

### 4. 설정 선택

- `conf/gen_verify.yaml`, `conf/verify_only.yaml`, `conf/replay_eval.yaml` 기본값에 추가하거나
- 실행 시 `-o` override로 선택

## 프런트 배포 번들 변환

엔진 산출물 `scene.json` 전체를 프런트로 그대로 보내지 않고, 별도 delivery 변환기로 경량 번들을 생성합니다.

- 입력: `artifacts/scenes/<scene_id>/<version_id>/scene.json`
- 출력: `artifacts/scenes/<scene_id>/<version_id>/delivery/spot_hidden_bundle.json`
- 번들 구조: `playable` + `answer_key`를 단일 JSON에 포함
- 프런트 응답 시에는 `answer_key`를 제거한 payload만 노출

변환 예시:

```bash
python -m delivery.spot_the_hidden.cli \
  --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json
```

이미지 전달 정책:

- 번들에는 이미지 바이너리 대신 `image_ref`만 포함
- 백엔드가 `image_ref`를 읽어 후처리 후 최종 이미지를 다시 참조로 관리
- `spot_hidden_v2` 번들은 `playable.layers`를 포함하며, `base/inpaint_patch/composite/fx_overlay` 레이어를 SSOT로 사용합니다.

## MLflow 필수 정책

모든 파이프라인은 tracker를 통해 실행 기록을 남깁니다.
기본 tracker는 `adapters/tracker=mlflow_file`이며, 실행 전 `--extra tracking` 설치가 필요합니다.

## 모델 구현 상태 메모

- `perception=hf`는 실제 HF 모델 추론 경로를 사용합니다.
- `hidden_region/inpaint/fx`의 `hf` 어댑터는 현재 placeholder 성격이 포함되어 있어, 품질/실추론 강화는 후속 구현 대상입니다.

## MinIO 등록 검증 스크립트

MinIO 저장 경로와 로컬 산출물 일치(해시) 및 Scene 역직렬화까지 한 번에 확인합니다.

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run python scripts/check_minio_scene_bundle.py \
  --scene-id <scene_id> \
  --version-id <version_id>
```

## 참고 문서

- `docs/pipeline-adapter-guide.md`
- `docs/handheld-ops-card.md`
- `docs/execution-contract.md`
