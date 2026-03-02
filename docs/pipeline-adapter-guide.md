# 파이프라인 어댑터 가이드

이 문서는 `discoverex`에서 모델/어댑터/설정 조합으로 파이프라인을 실행하고 확장하는 방법을 설명합니다.

## 1) 사전 조건
모든 파이프라인은 MLflow tracker를 사용합니다.

```bash
mkdir -p .cache/uv
UV_CACHE_DIR="$PWD/.cache/uv" uv venv .venv
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking
```

개발 검증까지 필요하면:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv sync --extra tracking --extra dev
```

## 2) 설정만으로 교체 가능한 범위
기존 파이프라인(`gen-verify`, `verify-only`, `replay-eval`)은 코드 수정 없이 아래를 교체할 수 있습니다.

- 모델 구현체: `conf/models/*`
- 저장소 구현체: `conf/adapters/artifact_store/*`, `conf/adapters/metadata_store/*`
- 트래커 구현체: `conf/adapters/tracker/*`
- Scene I/O 구현체: `conf/adapters/scene_io/*`
- 리포트 구현체: `conf/adapters/report_writer/*`
- 런타임/임계값/모델버전: `runtime`, `thresholds`, `model_versions`

## 3) 어댑터 구현 방법
포트 기준 파일:
- [`models port`](/home/esillileu/discoverex/engine/src/discoverex/application/ports/models.py)
- [`storage port`](/home/esillileu/discoverex/engine/src/discoverex/application/ports/storage.py)
- [`tracking port`](/home/esillileu/discoverex/engine/src/discoverex/application/ports/tracking.py)
- [`scene io port`](/home/esillileu/discoverex/engine/src/discoverex/application/ports/io.py)
- [`reporting port`](/home/esillileu/discoverex/engine/src/discoverex/application/ports/reporting.py)

구현 규칙:
1. 클래스 구현 위치: `src/discoverex/adapters/outbound/<group>/my_adapter.py`
2. use case에서 concrete adapter 직접 import 금지
3. Hydra `_target_` 등록: `conf/<models|adapters>/<group>/my_adapter.yaml`

예시:

```yaml
# @package adapters.tracker
_target_: discoverex.adapters.outbound.tracking.my_adapter.MyTrackerAdapter
```

## 4) 파이프라인 설정 파일 패턴
예시(`conf/gen_verify.yaml`):

```yaml
defaults:
  - models/hidden_region: dummy
  - models/inpaint: dummy
  - models/perception: dummy
  - models/fx: dummy
  - adapters/artifact_store: local
  - adapters/metadata_store: local_json
  - adapters/tracker: mlflow_file
  - adapters/scene_io: json
  - adapters/report_writer: local_json
  - runtime/model_runtime: gpu
  - runtime/env: default
  - _self_
```

`adapters/tracker`는 반드시 MLflow 구현을 가리키도록 유지합니다.

## 5) 기본 실행 방법
권장:

```bash
make sync
make run ARGS='discoverex gen-verify --background-asset-ref bg://dummy'
```

직접 실행:

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex gen-verify --background-asset-ref bg://dummy
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex verify-only --scene-json artifacts/scenes/<scene_id>/<version_id>/scene.json
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex replay-eval --scene-jsons artifacts/scenes/<scene_id>/<version_id>/scene.json
```

## 6) 실험용 파이프라인 만들고 실행하는 방법
새 실험 파이프라인(예: `ab-test`)은 아래 절차로 추가합니다.

1. Use case 추가
- 위치: `src/discoverex/application/use_cases/ab_test.py`
- 규칙: 포트/도메인만 의존, 직접 어댑터 import 금지

2. 패키지 export 추가
- `src/discoverex/application/use_cases/__init__.py`에서 공개 함수 export

3. CLI 명령 추가
- 파일: `src/discoverex/adapters/inbound/cli/main.py`
- 예: `@app.command("ab-test")`
- 입력 인자 파싱 후 `build_context(config=...)`로 context 생성하여 use case 호출

4. Hydra 설정 추가
- 파일: `conf/ab_test.yaml`
- `defaults`에 모델/어댑터/런타임 그룹을 선언
- tracker는 반드시 `adapters/tracker=mlflow_file` 또는 `mlflow_server`로 유지

5. 실행

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run discoverex ab-test --config-name ab_test
```

6. 외부 스케줄러 연동
- `docs/execution-contract.md` 계약에 따라 `command`, `args`, `overrides`를 전달

## 7) Scene Canonical 기준
캐논 계약 원문은 `canon.md`이며, 런타임 DTO/검증은 `src/discoverex/domain/*`가 담당합니다.

필수 가드레일:
- `regions[].geometry.bbox`는 `{x,y,w,h}` 객체
- `regions[].version` 필수
- `verification.final.failure_reason` 필수 문자열 (`pass=true`면 `""` 허용)
- `answer.answer_region_ids`는 `regions[].region_id` 부분집합

산출물 위치 예:
- `artifacts/scenes/{scene_id}/{version_id}/scene.json`
