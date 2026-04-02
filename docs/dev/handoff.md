# Developer Handoff

이 문서는 현재 저장소의 핵심 표면만 요약한다. 운영 절차는 `docs/ops`, 계약은 `docs/contracts`를 source of truth로 본다.

## 1. 저장소 현실

이 저장소는 문서 전용 workspace가 아니라 실제 엔진 실행 저장소다.

포함 범위:

- `discoverex` runtime package
- Prefect flow 엔트리포인트
- deployment/registration/sweep 운영 코드
- embedded worker stack
- contract, runtime, model 테스트

## 2. 가장 중요한 코드 표면

- 엔진 CLI: [src/discoverex/adapters/inbound/cli/main.py](/home/esillileu/discoverex/engine/src/discoverex/adapters/inbound/cli/main.py)
- Prefect runtime: [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)
- 공개 flow export: [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- ops control plane: [infra/ops](/home/esillileu/discoverex/engine/infra/ops)
- 운영 CLI: [scripts/cli](/home/esillileu/discoverex/engine/scripts/cli)

## 3. 현재 기능 형태

- `generate` 와 `verify` 가 가장 강한 런타임 경로다.
- `validate` 는 direct CLI validator 파이프라인이다.
- `serve` 는 animate dashboard 서버 표면이다.
- `animate` 는 public/runtime 표면에 포함되지만 구현 기대치는 보수적으로 유지해야 한다.
- `combined` flow 와 combined sweep 계열이 현재 코드와 테스트에 존재한다.

## 4. 먼저 확인할 것

```bash
just test
just run discoverex generate --background-asset-ref bg://dummy
./bin/cli prefect run gen
./bin/cli prefect sweep run --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

## 5. 문서 기준

- 사용법과 운영: [docs/ops/cli.md](/home/esillileu/discoverex/engine/docs/ops/cli.md)
- 런타임 경계: [docs/ops/runtime.md](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- 계약: [docs/contracts/orchestrator.md](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md)
- 과거 phase report 와 설계안: [docs/archive/README.md](/home/esillileu/discoverex/engine/docs/archive/README.md)
