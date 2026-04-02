# 문서 인덱스

현재 문서 체계는 역할별로 분리되어 있다. 상위 문서는 개요와 링크만 제공하고, 상세 규칙은 하위 문서에서만 설명한다.

## 1. 시작

- [README](/home/esillileu/discoverex/engine/README.md): 저장소 개요와 공개 표면
- [시작 가이드](/home/esillileu/discoverex/engine/docs/guide/getting-started.md): 설치, 최소 실행, 기본 검증

## 2. 운영

- [CLI 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/cli.md): `discoverex` 와 `./bin/cli` 사용법
- [런타임 가이드](/home/esillileu/discoverex/engine/docs/ops/runtime.md): local, worker, Prefect 실행 모델
- [Sweep 운영 가이드](/home/esillileu/discoverex/engine/docs/ops/sweeps.md): object-generation 및 combined sweep 운영

## 3. 계약

- [엔진 실행 계약](/home/esillileu/discoverex/engine/docs/contracts/engine-run.md): 엔진이 받는 실행 payload
- [오케스트레이터 계약](/home/esillileu/discoverex/engine/docs/contracts/orchestrator.md): Prefect flow 와 worker 경계
- [등록/배포 계약](/home/esillileu/discoverex/engine/docs/contracts/registration/README.md): deployment, registration, flow parameter 계약

## 4. 개발자 참고

- [Developer Handoff](/home/esillileu/discoverex/engine/docs/dev/handoff.md): 현재 저장소 상태와 주요 표면
- [Prefect 현재 상태](/home/esillileu/discoverex/engine/docs/dev/prefect-migration.md): Prefect 전환 완료 상태와 남은 caveat
- [Adapter Guide](/home/esillileu/discoverex/engine/docs/dev/adapters.md): 신규 adapter 추가 시 참고

## 5. 과거 문서

- [아카이브 안내](/home/esillileu/discoverex/engine/docs/archive/README.md)

`docs/archive` 아래 문서는 과거 설계안, phase report, 세션 메모, Validator 작업 노트 보존용이다. 현행 운영 절차나 계약의 source of truth로 사용하지 않는다.
