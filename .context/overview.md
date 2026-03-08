# Discoverex Context Index

이 문서는 `.context` 탐색 시작점입니다. 상세는 아래 문서를 우선 참고합니다.

## Primary Documents
- Canonical spec and architecture baseline:
  - `./canon.md`
- Current handoff and implementation status:
  - `./HANDOFF.md`
- Prefect migration status and decision log:
  - `./prefect-migration-assessment.md`
  - `./prefect-migration-task-breakdown.md`

## Document Roles
- `canon.md`: 제품/아키텍처의 기준 계약(SSOT)
- `HANDOFF.md`: 현재 구현 상태, 검증 결과, 후속 작업
- `prefect-migration-assessment.md`: Prefect 전환 평가/리스크/운영 권고
- `prefect-migration-task-breakdown.md`: 실행 단위 작업 분해와 완료 기준

## Usage Rule
1. 계약/아키텍처 판단은 `canon.md`를 우선 확인합니다.
2. 현재 코드 기준 상태/검증 근거는 `HANDOFF.md`를 확인합니다.
3. Prefect 전환 범위/잔여 작업은 `prefect-migration-*` 문서를 확인합니다.

## Scope
- 이 파일에는 긴 실행 로그/상세 절차를 기록하지 않습니다.
- 상세 내용은 각 원문 문서에만 유지합니다.
