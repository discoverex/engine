# Prefect Migration Assessment (v2 + v1 Shim)

## 결론
- 이 레포는 Prefect 기반 DAG 실행 모델로 전환 가능하다.
- 기존 hexagonal 경계(application/domain의 프레임워크 중립)와 충돌 없이 적용 가능하다.
- 다만 외부 계약은 `v2(generate/verify/animate)`로 승격하고 `v1` shim을 동시에 유지해야 안전하다.

## 확인된 사실
- 기존 외부 계약은 `v1 + gen-verify/verify-only/replay-eval` 중심이다.
- Prefect flow는 있었지만(`orchestrator/prefect_flows.py`) 엔진 내부 SSOT가 아니라 래퍼였다.
- Hydra는 이미 모델/어댑터 조립에 사용되고 있으며 flow 조립 확장이 가능하다.
- `animate`는 실 구현이 없어 초기에는 stub로 노출하는 것이 현실적이다.

## 적용 원칙
- 외부 계약(canon envelope)은 안정 유지, 실행 모델만 Prefect로 전환.
- flow는 orchestration 책임만 가지며 실제 로직은 application use case 호출 유지.
- Prefect 메타데이터는 주 계약이 아니라 확장 metadata로만 취급.

## 리스크
- v2 전환 시 오케스트레이터/운영 스크립트의 command 명세 동기화 필요.
- `animate`의 stub 상태를 명확히 공지하지 않으면 운영 혼선 위험.
- Prefect 의존성 추가에 따른 런타임 이미지/락파일 동기화 필요.

## 운영 권고
- 배포 1차: `generate/verify` 실동작 + `animate` stub + v1 shim.
- 배포 2차: animate 실제 use case 연결 및 subflow 세분화(재시도/병렬 가치 구간 우선).
