# Prefect Migration Status & History

Discoverex 엔진의 Prefect 기반 실행 모델 전환 과정과 현재 상태를 기록합니다.

## 1. 개요 및 목적

기존의 단순 프로세스 래퍼에서 Prefect Flow/Task 기반의 인프로세스(In-process) 라우터 모델로 전환하여 다음을 달성합니다.
- 외부 Prefect UI에서 태스크/서브플로우의 가시성 확보.
- 워커 실행의 관측성 및 디버깅 용이성 개선.
- 세밀한 재시도 및 병렬 실행 제어 기반 마련.

## 2. 마이그레이션 진행 현황 (Update)

### 완료된 작업 (Baseline)
- [x] **v2 명령어 도입**: `generate`, `verify`, `animate` 명령을 공식 지원합니다.
- [x] **v1 Shim 유지**: `gen-verify` 등 레거시 명령의 하위 호환성을 유지합니다.
- [x] **인프로세스 라우터**: `prefect_flow.py`에서 서브프로세스 래퍼 대신 `engine_entry_flow`를 호출합니다.
- [x] **태스크 분해**: `generate`와 `verify` 경로를 Prefect 태스크 단위로 세분화했습니다.
- [x] **임포트 타임 의존성 제거**: 워커에서 Flow 로드 시 Hydra 등 무거운 의존성으로 인해 발생하는 충돌을 Lazy Import로 해결했습니다.

### 잔여 작업 및 마일스톤
- [ ] `animate` 실 유스케이스 구현 및 Stub 제거.
- [ ] 운영 Prefect 환경에서의 E2E 스모크 테스트 자동화.
- [ ] 레거시 Shim Sunset 정책 수립 (지원 중단 시점 공지).

## 3. 마이그레이션 평가 및 리스크

### 현재 상태 요약
- 엔진은 이제 Prefect 기반 실행 모델로 완전히 전환되었으며, `generate/verify` 파이프라인은 실동작이 확인되었습니다.
- 외부 오케스트레이터와의 계약은 `v2` 명령어를 기준으로 일원화되었습니다.

### 주요 리스크
- `animate`의 미구현으로 인해 전체 기능 완결성이 아직 확보되지 않았습니다.
- 워커 런타임 이미지와 엔진의 애플리케이션 의존성 간의 정합성 유지를 위한 지속적인 관리가 필요합니다.

## 4. 디버깅 및 최근 사실 (Debug Status)

- **공식 엔트리포인트**:
  - `prefect_flow.py:run_generate_job_flow`
  - `prefect_flow.py:run_verify_job_flow`
  - `prefect_flow.py:run_animate_job_flow`
  - `prefect_flow.py:run_combined_job_flow`
- **로컬 워커 확인**: 로컬 컨테이너 기반 워커에서 `hydra` 의존성 문제 없이 플로우 로딩이 가능함을 확인했습니다.
- **가시성 확보**: 외부 Prefect UI에서 태스크 레코드가 정상적으로 생성되고 서브플로우 트리가 표시됩니다.

## 5. 참고 문서
- 실행 계약 (External): `docs/contracts/orchestrator.md`
- 현재 실행 능력 및 제약: `.context/capabilities.md`
