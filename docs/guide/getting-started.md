# 시작 가이드

이 문서는 현재 저장소를 처음 다룰 때 필요한 최소 단계만 설명한다. 세부 명령 옵션은 [CLI 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/cli.md)를 본다.

## 1. 준비

- Python 3.11+
- `uv`
- `just`

기본 설치:

```bash
just init
```

## 2. 가장 짧은 로컬 실행

장면 생성:

```bash
just run discoverex generate --background-asset-ref bg://dummy
```

CPU 프로필 예시:

```bash
just run discoverex generate --background-asset-ref bg://dummy -o profile=cpu_fast
```

검증 예시:

```bash
just run discoverex verify --scene-json artifacts/.../scene.json
```

Validator 예시:

```bash
just run discoverex validate composite.png --object-layer obj1.png --object-layer obj2.png
```

## 3. Prefect 운영 진입점

표준 job submission:

```bash
./bin/cli prefect run gen
```

Sweep 실행:

```bash
./bin/cli prefect sweep run --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

Sweep 수집:

```bash
./bin/cli prefect sweep collect --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

## 4. 기본 검증

```bash
just lint
just typecheck
just test
uv run discoverex e2e --scenario all
```

## 5. 다음에 볼 문서

- 실행 표면과 옵션: [docs/ops/cli.md](/home/esillileu/discoverex/engine/docs/ops/cli.md)
- 런타임 차이: [docs/ops/runtime.md](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- sweep 운영: [docs/ops/sweeps.md](/home/esillileu/discoverex/engine/docs/ops/sweeps.md)
- 계약: [docs/contracts/orchestrator.md](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md)
