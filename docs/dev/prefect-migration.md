# Prefect 현재 상태

이 문서는 이 저장소가 이미 Prefect-first 실행 모델로 전환된 상태임을 짧게 정리한다. 운영 방법은 `docs/ops`, 계약 경계는 `docs/contracts`를 기준으로 본다.

## 1. 현재 baseline

이미 구현된 기준선:

- `prefect_flow.py` 공개 callable
- `infra/ops` 아래 deployment, registration, submission, sweep 운영 코드
- `infra/prefect` 아래 worker/runtime 실행 경로
- `discoverex-combined-flow` 를 포함한 composite execution path
- worker-managed artifact persistence

## 2. 현재 안정 표면

flow 이름:

- `discoverex-engine-flow`
- `discoverex-generate-flow`
- `discoverex-verify-flow`
- `discoverex-animate-flow`
- `discoverex-combined-flow`

운영 wrapper 표면:

- `./bin/cli prefect run gen`
- `./bin/cli prefect run obj`
- `./bin/cli prefect sweep run --sweep-spec <path>`
- `./bin/cli prefect sweep collect --sweep-spec <path>`

## 3. 현재 범위

현재 코드와 spec 기준으로 다음이 존재한다.

- 목적 기반 deployment naming
- object-generation sweep
- combined replay fixture sweep
- naturalness/patch-selection/inpaint 계열 combined sweep

## 4. 남은 caveat

- `animate` 는 아직 완전한 production animation pipeline으로 간주하지 않는다.
- 호환 alias는 남아 있지만 주 표면은 아니다.

## 5. 관련 파일

- [prefect_flow.py](/home/esillileu/discoverex/engine/prefect_flow.py)
- [infra/prefect/flow.py](/home/esillileu/discoverex/engine/infra/prefect/flow.py)
- [scripts/cli/prefect.py](/home/esillileu/discoverex/engine/scripts/cli/prefect.py)
- [docs/ops/sweeps.md](/home/esillileu/discoverex/engine/docs/ops/sweeps.md)
