# Discoverex Core Engine

Discoverex Core Engine는 숨은 오브젝트 장면 생성, 검증, Prefect 기반 실행을 담당하는 실행 저장소다. 엔진 CLI, Prefect flow 엔트리포인트, worker 운영 도구, sweep/registration 스펙이 이 저장소에 함께 들어 있다.

## 프로젝트가 하는 일

- 배경 자산 또는 프롬프트를 기반으로 숨은 오브젝트 장면을 생성한다.
- 생성된 장면을 검증하고 결과 아티팩트를 기록한다.
- 로컬 CLI 실행과 Prefect-managed worker 실행을 모두 지원한다.
- object generation sweep과 combined replay/naturalness sweep을 운영한다.

## 현재 공개 표면

### 엔진 CLI

패키지는 `discoverex` CLI를 제공한다.

- `generate`
- `verify`
- `animate`
- `validate`
- `serve`
- `e2e`

숨겨진 호환 명령도 남아 있다.

- `gen-verify`
- `verify-only`
- `replay-eval`

### Prefect flow 엔트리포인트

루트 모듈 [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py) 에서 다음 callables를 공개한다.

- `run_job_flow`
- `run_generate_job_flow`
- `run_verify_job_flow`
- `run_animate_job_flow`
- `run_combined_job_flow`

등록되는 flow 이름은 다음과 같다.

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

### 운영 CLI

`./bin/cli`는 운영용 래퍼다.

- `./bin/cli prefect`
- `./bin/cli worker`
- `./bin/cli artifacts`
- `./bin/cli legacy`

주요 운영 표면은 목적 기반 deployment와 sweep 실행이다.

- `./bin/cli prefect run gen|obj`
- `./bin/cli prefect sweep run|collect`
- `./bin/cli prefect deploy flow ...`
- `./bin/cli prefect register flow ...`

## 저장소 레이아웃

- [src/discoverex](/home/esillileu/discoverex/engine/src/discoverex): 엔진 애플리케이션, 도메인, 어댑터, CLI
- [conf](/home/esillileu/discoverex/engine/conf): Hydra 설정과 프로필
- [infra/prefect](/home/esillileu/discoverex/engine/infra/prefect): Prefect runtime 과 flow 로직
- [infra/ops](/home/esillileu/discoverex/engine/infra/ops): deployment, registration, sweep, spec 운영 코드
- [infra/worker](/home/esillileu/discoverex/engine/infra/worker): 내장 worker 스택
- [tests](/home/esillileu/discoverex/engine/tests): 계약, 런타임, sweep, E2E 테스트

## 빠른 시작

```bash
just init
just run discoverex generate --background-asset-ref bg://dummy
./bin/cli prefect run gen
```

검증 커맨드:

```bash
just lint
just typecheck
just test
```

## 문서 맵

- [문서 인덱스](/home/esillileu/discoverex/engine/docs/guide/doc-map.md)
- [시작 가이드](/home/esillileu/discoverex/engine/docs/guide/getting-started.md)
- [CLI 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/cli.md)
- [런타임 가이드](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- [Sweep 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/sweeps.md)
- [엔진 실행 계약](/home/esillileu/discoverex/engine/docs/contracts/engine-run.md)
- [오케스트레이터 계약](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md)
- [등록/배포 계약](/home/esillileu/discoverex/engine/docs/contracts/registration/README.md)
- [개발자 현재 상태](/home/esillileu/discoverex/engine/docs/dev/handoff.md)

## 보조 컨텍스트

`.context/` 아래 문서는 보조 참고 자료다. 운영 절차나 계약의 source of truth는 `docs/ops` 와 `docs/contracts`를 우선한다.
