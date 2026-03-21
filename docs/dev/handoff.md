# HANDOFF (Current Status & Next Steps)

이 문서는 프로젝트의 최신 상태를 기록하고 다음 작업자가 이어서 진행할 수 있도록 정보를 제공합니다.

## 1. 현재 상태 스냅샷 (Snapshot)

- **핵심 아키텍처**: 헥사고널 아키텍처 및 Scene 캐논 스펙 v1 기반.
- **실행 모델**: Prefect 기반 v2 명령어(`generate`, `verify`, `animate`) 일원화 완료.
- **로컬 검증**: `ruff`, `mypy`, `pytest` 등 모든 품질 가드 통과.

## 2. 최근 주요 변경 사항

### Prefect 마이그레이션 (v2 baseline)
- 엔진 명령어 체계를 v2로 전환하고 v1 Shim을 지원합니다.
- `engine_entry_flow`를 통한 플로우 디스패치 구조를 도입했습니다.
- `generate` 및 `verify` 플로우를 Prefect 태스크 단위로 세밀하게 분해했습니다.
- `orchestrator_contract`에서 실행 로직을 제거하고, 공통 런타임/업로드/트래킹 로직을 `application/services`와 `adapters/outbound`로 이동했습니다.

### 현재 플로우 분류
- 외부 엔트리포인트: `discoverex-engine-flow`, `discoverex-generate-flow`, `discoverex-verify-flow`, `discoverex-animate-flow`, `discoverex-combined-flow`
- 내부 엔진 플로우: `discoverex-engine-entry-pipeline`, `discoverex-generate-pipeline`, `discoverex-verify-pipeline`, `discoverex-generate-inpaint-variant-pack`
- 내부/호환 핸들러: `generate_v1_compat`, `generate_v2_compat`, `generate_verify_v2`, `generate_object_only`, `generate_inpaint_variant_pack`, `verify_v1_compat`, `animate_replay_eval`, `animate_stub`

### 오류 페이로드 정규화
- 플로우에서 예외 발생 시 표준 오류 페이로드(`status=failed`, `failure_reason`)를 반환하도록 수정했습니다.

## 3. 운영 모드 (Operational Model)
- **로컬 모드 (기본)**: 로컬 파일 시스템 저장소 및 MLflow 로컬 모드 사용.
- **워커 모드 (권장)**: 워커가 `MLFLOW_TRACKING_URI`와 engine artifact dir/manifest 경로를 주입하고, 업로드와 MLflow artifact URI 기록을 담당합니다.

## 4. 잔여 작업 및 공백 (Next Steps)

1. **`animate` 실 유스케이스 구현**: 현재 Stub 상태인 애니메이션 파이프라인의 실질적 구현 및 검증.
2. **플로우 명칭 정리**: `*_compat` handler와 v1 shim을 언제 제거할지 정책 결정.
3. **E2E 스모크 테스트 자동화**: 운영 Prefect 서버 환경에서 전체 파이프라인이 정상적으로 동작하는지 확인하는 자동화 시나리오 추가.

## 5. 중요 명령어

- **환경 구축**: `uv sync --extra tracking --extra dev`
- **품질 검사**: `just lint`, `just typecheck`, `just test`
- **직접 실행**: `just run discoverex generate --background-asset-ref bg://dummy`

## 6. 참고 파일
- 상세 아키텍처 가이드: `.context/architecture.md`
- 마이그레이션 이력: `docs/dev/prefect-migration.md`
- 현재 실행 능력 및 제약: `.context/capabilities.md`
