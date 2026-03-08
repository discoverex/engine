# Prefect Migration Assessment (Current)

## 결론
- 엔진은 Prefect 기반 실행 모델로 전환되었고, 현재는 **부분 완성 상태**다.
- `generate/verify`는 실동작 구현됨.
- `animate`는 의도적으로 stub 유지.

## 현재 상태 요약
- 외부 계약: `v2(generate/verify/animate)` 기준, `v1` shim 지원.
- 엔트리 흐름: `engine_entry_flow`에서 command dispatch.
- 내부 구성:
  - `generate`: 핵심 단계를 Prefect flow/task로 조립.
  - `verify`: scene load/context/use case 경로를 Prefect 단계화.
  - `animate`: 실패 payload 반환 stub.

## 호환성
- 레거시 명령은 동작 유지하되 deprecation 경고를 출력.
- canonical result envelope는 유지.
- entry flow에서 예외 발생 시 canonical failure payload 반환.

## 리스크
- `animate` 미구현으로 제품 완결성은 미충족.
- 실제 운영 Prefect deployment 상에서 추가 smoke 검증 필요.
- 일부 HF 어댑터 placeholder 성격은 품질 리스크로 남아 있음.

## 운영 권고
- 단기: `generate/verify`를 운영 기준선으로 사용.
- 중기: `animate` 실구현 + worker/deployment E2E 검증.
- 장기: shim sunset 정책(시점/공지/차단 기준) 수립.
