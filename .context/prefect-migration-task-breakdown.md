# Prefect Migration Task Breakdown (Updated)

## 목표 상태
- 상위 flow는 `generate/verify/animate`로 고정.
- `generate/verify`는 Prefect 단계형 구현 완료.
- `animate`는 stub 유지(명시적 범위 제외).

## 진행 현황
- [x] A1. `orchestrator_contract` v2 command 도입 (`generate/verify/animate`).
- [x] A2. v1 shim 매핑 유지 (`gen-verify/verify-only/replay-eval`).
- [x] A3. runner CLI 토큰을 v2 command로 일원화.
- [x] A4. launcher 입력 검증이 v1/v2 union 수용.

- [x] B1. `engine_entry_flow` 도입 및 command dispatch 적용.
- [x] B2. `generate` Prefect stage flow 구현.
- [x] B3. `verify` Prefect stage flow 구현.
- [x] B4. `animate` stub 정책 유지.

- [x] C1. `conf/flows/generate|verify|animate` 그룹 반영.
- [x] C2. 기존 config(`gen_verify/verify_only/replay_eval`) shim 경로 유지.
- [x] C3. 신규 config alias(`generate/verify/animate`) 반영.
- [x] C4. `PipelineConfig`에 `flows` 스키마 반영.

- [x] D1. CLI 공개 명령을 `generate/verify/animate`로 전환.
- [x] D2. legacy 명령은 hidden alias 유지.
- [x] D3. 등록 스크립트 v2 기본 전환.
- [x] D4. launcher/CLI에서 legacy deprecation 경고 출력.

- [x] E1. 계약 테스트(v2 + v1 shim) 반영.
- [x] E2. 런처 테스트(uv/pip + shim + warning) 반영.
- [x] E3. 등록 스크립트 테스트(v2 기본 + v1 허용) 반영.
- [x] E4. 아키텍처 가드(경계/line cap) 통과.

## 잔여 작업
- [ ] F1. `animate` 실 유스케이스 구현 및 stub 제거.
- [ ] F2. 운영 Prefect deployment 기반 E2E smoke 자동화.
- [ ] F3. shim sunset 정책 문서화(차단 시점/마이그레이션 안내).
