# Discoverex CLI 운영 가이드

이 문서는 현재 지원되는 CLI 표면만 설명한다. 런타임 책임은 [런타임 가이드](/home/esillileu/discoverex/engine/docs/ops/runtime.md), 계약은 [오케스트레이터 계약](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md)을 본다.

## 1. CLI 표면

이 저장소에는 두 개의 CLI 표면이 있다.

- `discoverex`: 엔진 실행 CLI
- `./bin/cli`: Prefect, worker, artifact 운영 CLI

## 2. 엔진 CLI: `discoverex`

구현 위치: [src/discoverex/adapters/inbound/cli/main.py](/home/esillileu/discoverex/engine/src/discoverex/adapters/inbound/cli/main.py)

### 공개 명령

- `generate`
- `verify`
- `animate`
- `validate`
- `serve`
- `e2e`

### `generate`

장면 생성 파이프라인을 실행한다.

```bash
uv run discoverex generate --background-asset-ref bg://dummy
uv run discoverex generate --background-prompt "kitchen interior" --object-prompt "red mug"
```

중요 옵션:

- `--background-asset-ref`
- `--background-prompt`
- `--object-prompt`
- `--final-prompt`
- `--config-name`
- `--config-dir`
- `-o`, `--override`
- `--verbose`

`--background-asset-ref` 또는 `--background-prompt` 중 하나는 필수다.

### `verify`

기존 `scene.json`을 검증한다.

```bash
uv run discoverex verify --scene-json artifacts/.../scene.json
```

### `animate`

애니메이션 엔트리포인트를 실행한다.

```bash
uv run discoverex animate --scene-jsons artifacts/.../scene.json
uv run discoverex animate --image-path input.png
```

현재 public command 와 Prefect wiring 은 존재하지만, 내부 구현은 여전히 replay/stub 성격의 핸들러에 의존한다.

### `validate`

합성 이미지와 object layer PNG들을 대상으로 validator 파이프라인을 실행한다.

```bash
uv run discoverex validate composite.png --object-layer obj1.png --object-layer obj2.png
```

이 명령은 direct CLI 전용이다.

### `serve`

animate dashboard 웹 서버를 실행한다.

```bash
uv run discoverex serve --host 0.0.0.0 --port 5001
```

기본 설정은 `animate_comfyui` config를 사용한다.

### `e2e`

로컬 런타임 계약 harness를 실행한다.

```bash
uv run discoverex e2e --scenario all
uv run discoverex e2e --scenario live-services --ensure-live-infra
```

지원 시나리오:

- `tracking-artifact`
- `worker-contract`
- `live-services`
- `all`

### 숨겨진 호환 명령

숨겨진 명령은 남아 있지만 주 사용 표면은 아니다.

- `gen-verify` -> `generate`
- `verify-only` -> `verify`
- `replay-eval` -> `animate`

## 3. 운영 CLI: `./bin/cli`

구현 위치: [scripts/cli/main.py](/home/esillileu/discoverex/engine/scripts/cli/main.py)

서브커맨드:

- `prefect`
- `worker`
- `artifacts`
- `legacy`

## 4. `./bin/cli prefect`

구현 위치: [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)

### 목적 기반 deployment 기본값

- `standard` -> `gpu-fixed`
- `batch` -> `gpu-fixed-batch`
- `debug` -> `gpu-fixed-debug`
- `backfill` -> `gpu-fixed-backfill`

flow-kind deployment 이름:

- `discoverex-generate-<purpose>`
- `discoverex-verify-<purpose>`
- `discoverex-animate-<purpose>`
- `discoverex-combined-<purpose>`

### 표준 flow deploy/register

```bash
./bin/cli prefect deploy flow generate --purpose standard
./bin/cli prefect deploy flow combined --purpose batch
./bin/cli prefect register flow generate --purpose standard
./bin/cli prefect register flow combined --purpose batch
```

### 표준 job 실행

```bash
./bin/cli prefect run --spec infra/ops/specs/job/generate_verify.standard.yaml
./bin/cli prefect run gen
./bin/cli prefect run obj
```

기본 규칙:

- bare `run`은 `--spec`이 필요하다
- `run gen` 과 `run obj`는 모두 `discoverex-generate-standard`를 기본 deployment로 사용한다
- 기본 spec은 `infra/ops/specs/job/generate_verify.standard.yaml` 이다
- 필요하면 `--deployment`, `--work-queue-name`, `--spec` 으로 override 가능하다

### sweep 실행과 수집

```bash
./bin/cli prefect sweep run --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
./bin/cli prefect sweep collect --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

이 표면은 다음을 포함한다.

- object-generation sweep
- combined replay fixture sweep
- naturalness/patch-selection/inpaint 계열 combined sweep

운영 규칙과 spec shape는 [Sweep 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/sweeps.md)를 본다.

### experiment deployment

```bash
./bin/cli prefect deploy experiment --experiment naturalness --purpose batch
```

### raw spec 도구

```bash
./bin/cli prefect build-spec ...
./bin/cli prefect submit-spec path/to/job.yaml
./bin/cli prefect check-logs <FLOW_RUN_ID>
./bin/cli prefect inspect-run <FLOW_RUN_ID>
```

## 5. `./bin/cli worker fixed`

구현 위치: [scripts/cli/worker.py](/home/esillileu/discoverex/engine/scripts/cli/worker.py)

주요 명령:

- `./bin/cli worker init`
- `./bin/cli worker fixed up`
- `./bin/cli worker fixed down`
- `./bin/cli worker fixed ps`
- `./bin/cli worker fixed logs --tail 120 -f`
- `./bin/cli worker fixed build`
- `./bin/cli worker fixed doctor`

이 표면은 [infra/worker](/home/esillileu/discoverex/engine/infra/worker) 아래 내장 Docker worker 스택을 조작한다.

## 6. 세부 spec 위치

- job spec 구조: [infra/ops/specs/job/README.md](/home/esillileu/discoverex/engine/infra/ops/specs/job/README.md)
- sweep spec 구조: [infra/ops/specs/sweep/README.md](/home/esillileu/discoverex/engine/infra/ops/specs/sweep/README.md)
