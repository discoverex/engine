# Prefect Migration Task Breakdown

## 목표 상태
- 엔진 진입은 상위 flow `generate/verify/animate`로 통일된다.
- 하위 실행 경로는 Hydra 설정으로 조립 가능하다.
- 외부 `v1` 호출은 shim으로 계속 수용된다.

## 작업 묶음 A: 계약/진입점
- [ ] A1. `orchestrator_contract`에 `v2` command 추가(`generate/verify/animate`).
- [ ] A2. `v1` command(`gen-verify/verify-only/replay-eval`) shim 매핑 유지.
- [ ] A3. runner가 실제 CLI 토큰을 v2 command로 생성하도록 일원화.
- [ ] A4. launcher 입력 검증이 v1/v2 union을 수용하도록 갱신.

완료기준:
- `build_cli_tokens`가 v1 입력도 정상적으로 v2 CLI로 변환.
- launcher 단위 테스트에서 v1/v2 모두 실행 경로 통과.

## 작업 묶음 B: Prefect 엔진 플로우
- [ ] B1. `src/discoverex/flows/engine.py`에 entry flow 도입.
- [ ] B2. 상위 command별 subflow 핸들러 해석 로직 구현.
- [ ] B3. `src/discoverex/flows/subflows.py`에 generate/verify/animate 구현체 연결.
- [ ] B4. `animate`는 1차에서 stub 반환 정책 적용.

완료기준:
- `run_engine_entry(command=...)`로 3개 상위 flow 호출 가능.
- flow 계층은 use case만 호출하고 business 로직 직접 포함하지 않음.

## 작업 묶음 C: Hydra 조립
- [ ] C1. `conf/flows/generate|verify|animate` 그룹 추가.
- [ ] C2. 기존 config(`gen_verify/verify_only/replay_eval`)에 flow 조립 기본값 포함.
- [ ] C3. 신규 config alias(`generate/verify/animate`) 제공.
- [ ] C4. `PipelineConfig`에 `flows` 스키마 추가.

완료기준:
- Hydra override로 flow 구현체 교체 가능(`-o flows/animate=replay_eval` 등).
- config 로드 시 타입 검증 오류 없음.

## 작업 묶음 D: CLI/운영 진입점
- [ ] D1. CLI 공개 명령을 `generate/verify/animate`로 전환.
- [ ] D2. legacy 명령은 hidden alias로 유지.
- [ ] D3. job 등록 스크립트 default를 `v2`로 전환.
- [ ] D4. script에서 `--contract-version` 기반 command 유효성 검사.

완료기준:
- 신규 명령으로 실행 가능.
- 레거시 입력도 워커 경로에서 실패 없이 매핑됨.

## 작업 묶음 E: 검증
- [ ] E1. 계약 테스트: v2 validate + v1 shim 변환.
- [ ] E2. 런처 테스트: uv/pip 경로 + shim 시나리오.
- [ ] E3. 등록 스크립트 테스트: v2 기본 + v1 허용.
- [ ] E4. 아키텍처 테스트: application에 Prefect import 없음 확인.

완료기준:
- 관련 테스트 전부 green.
- 실패 시 계약/매핑/타입 검증 중 원인 분류 로그 남김.

## 후속(2차)
- [ ] F1. `animate` 실 유스케이스 도입(현재 stub 대체).
- [ ] F2. generate/verify 내부를 가치 기반으로 subflow/task 세분화.
- [ ] F3. 실행 관측 지표(run/task metadata) 표준화.
