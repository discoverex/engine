# Orchestrator & Worker Contract (Prefect)

이 문서는 외부 오케스트레이터가 엔진 작업을 요청할 때 사용하는 사양인 `JobSpec`을 정의합니다.

## 1. 개요 및 엔트리포인트

- **공식 플로우 엔트리포인트**:
  - `prefect_flow.py:run_generate_job_flow`
  - `prefect_flow.py:run_verify_job_flow`
  - `prefect_flow.py:run_animate_job_flow`
  - `prefect_flow.py:run_combined_job_flow`
- **Prefect 플로우 이름**:
  - `discoverex-generate-flow`
  - `discoverex-verify-flow`
  - `discoverex-animate-flow`
  - `discoverex-combined-flow`

### 책임 경계
- **엔진 저장소**: 등록 가능한 플로우 호출부와 런타임 호환성을 책임집니다.
- **외부 운영 계층**: Deployment 생성, 작업 제출(Submission), 워커 풀 및 큐 관리를 책임집니다.

## 2. Job Spec 스키마 (`job_spec_json`)

워커가 작업을 실행하기 위해 수신하는 JSON 페이로드의 주요 필드입니다.

- `engine`: 엔진 식별자 (예: "discoverex")
- `repo_url`: 실행할 엔진 리포지토리 URL
- `ref`: 특정 브랜치, 태그 또는 SHA 값
- `entrypoint`: 실행할 명령 리스트 (예: `["python", "-m", "..."]`)
- `inputs`: `EngineRunSpec`을 포함하는 실제 작업 입력 (명령어, 인자 등)
- `env`: 워커 수준에서 주입할 환경변수

## 3. 워커 실행 환경 (Runtime Environment)

워커가 자식 엔진 프로세스에 제공해야 하는 정보입니다.
- `ORCH_JOB_INPUTS_JSON`: 위 `JobSpec`의 `inputs` 부분.
- `ORCH_ENGINE_ARTIFACT_DIR`: 워커가 만든 엔진 산출물 로컬 디렉터리.
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`: 엔진이 작성할 manifest JSON 경로.
- `MLFLOW_TRACKING_URI`: 워커가 직접 주입하는 MLflow URI. 필요하면 워커가 프록시 주소로 치환합니다.

워커는 엔진 stdout에서 구조화 JSON 한 줄을 읽어 실행 결과를 연결합니다.
- `mlflow_run_id`가 포함되면 워커는 그 run에 업로드 결과 URI tag를 기록합니다.
- 엔진은 MLflow run을 재조회하지 않습니다.

## 4. 아티팩트 및 결과 구조

실행이 완료되면 아래와 같은 구조로 결과가 영속화됩니다.
- `jobs/{flow_run_id}/attempt-{n}/stdout.log`
- `jobs/{flow_run_id}/attempt-{n}/stderr.log`
- `jobs/{flow_run_id}/attempt-{n}/result.json`
- `jobs/{flow_run_id}/attempt-{n}/artifacts.json`

엔진 전용 durable artifact가 있으면 추가 계약은 다음과 같습니다.
- 엔진은 `ORCH_ENGINE_ARTIFACT_DIR` 아래에만 파일을 씁니다.
- 엔진은 `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`에 manifest를 씁니다.
- 워커가 manifest를 읽고 업로드를 수행합니다.
- 워커가 업로드된 object URI를 MLflow tag로 기록합니다.
- presign 요청과 MinIO 업로드는 워커가 수행합니다.

## 5. 참고 문서
- 내부 엔진 실행 사양: `docs/contracts/engine-run.md`
- 마이그레이션 이력: `docs/dev/prefect-migration.md`
