# Discoverex 런타임 가이드

이 문서는 엔진이 local, worker, Prefect 환경에서 어떻게 실행되는지 설명한다. CLI 사용법은 [CLI 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/cli.md), worker/env 계약은 [등록/배포 계약](/home/esillileu/discoverex/engine/docs/contracts/registration/README.md)을 본다.

## 1. 실행 모드

### Local mode

개발과 직접 CLI 실행에 사용한다.

- 엔트리포인트: `uv run discoverex ...`
- inline job spec runtime mode: `local`
- 일반적인 저장 위치: `artifacts/`
- 일반적인 tracking: local MLflow 또는 명시적으로 지정한 tracking URI

### Worker mode

Prefect flow가 엔진을 실행할 때 사용한다.

- 엔트리포인트: [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py) 공개 callable
- 실제 runtime 준비: [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)
- worker-managed artifact 와 MLflow linkage 적용
- control plane submission/deployment 는 [infra/ops](/home/esillileu/discoverex/engine/infra/ops) 에 존재

## 2. 공개 실행 명령과 역할

엔진 런타임에서 공개된 명령:

- `generate`
- `verify`
- `animate`
- `validate`
- `serve`
- `e2e`

운영 계약상 핵심 실행 경로:

- `generate`
- `verify`
- `animate`
- `combined` Prefect flow

실행 성격:

- `validate` 는 direct CLI-only validator 파이프라인이다.
- `serve` 는 animate dashboard 서버 실행용이다.
- `e2e` 는 계약 smoke harness다.
- `discoverex-combined-flow` 는 composite execution path이며 `gen-verify`를 explicit sequence로 분해할 수 있다.

## 3. Prefect flow 표면

외부 공개 flow 이름:

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

내부 엔진 flow 이름:

- `discoverex-engine-entry-pipeline`
- `discoverex-generate-pipeline`
- `discoverex-verify-pipeline`
- `discoverex-generate-inpaint-variant-pack`

## 4. worker가 제공하는 런타임 경계

Prefect 실행 시 worker/runtime 레이어는 다음 환경값을 제공할 수 있다.

- `ORCH_JOB_INPUTS_JSON`
- `ORCH_ENGINE_ARTIFACT_DIR`
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`
- `MLFLOW_TRACKING_URI`

이 값들의 의미와 책임은 [docs/contracts/registration/runtime-auth-and-env.md](/home/esillileu/discoverex/engine/docs/contracts/registration/runtime-auth-and-env.md) 와 [docs/contracts/registration/artifact-persistence-contract.md](/home/esillileu/discoverex/engine/docs/contracts/registration/artifact-persistence-contract.md)에 정의한다.

## 5. 로컬 실행 예시

```bash
just run discoverex generate --background-asset-ref bg://dummy
just run discoverex verify --scene-json artifacts/.../scene.json
just run discoverex validate composite.png --object-layer obj1.png --object-layer obj2.png
uv run discoverex serve --port 5001
```

## 6. worker 디버그 예시

```bash
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
ORCH_ENGINE_ARTIFACT_DIR="$PWD/.tmp/engine-artifacts" \
ORCH_ENGINE_ARTIFACT_MANIFEST_PATH="$PWD/.tmp/engine-artifacts.json" \
uv run discoverex generate \
  --background-asset-ref bg://dummy \
  -o adapters/tracker=mlflow_server
```

## 7. embedded fixed worker

내장 worker 스택은 [infra/worker/README.md](/home/esillileu/discoverex/engine/infra/worker/README.md)에 문서화되어 있다.

대표 명령:

```bash
./bin/cli worker init
./bin/cli worker fixed up
./bin/cli worker fixed logs --tail 120 -f
./bin/cli worker fixed doctor --json
```

## 8. sweep 런타임 위치

sweep 제출과 수집은 운영 표면상 `./bin/cli prefect sweep run|collect` 로 노출된다.

현재 지원 범위:

- object-generation sweep
- combined replay fixture sweep
- naturalness/patch-selection/inpaint 계열 combined sweep

세부 운영 규칙은 [docs/ops/sweeps.md](/home/esillileu/discoverex/engine/docs/ops/sweeps.md)를 본다.

## 9. 현재 caveat

- `generate` 와 `verify` 가 가장 완성도가 높다.
- `animate` 는 public/runtime 표면에는 포함되지만 내부 구현은 아직 보수적으로 다뤄야 한다.
