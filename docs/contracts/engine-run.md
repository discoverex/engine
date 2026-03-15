# Engine Run Contract

이 문서는 엔진이 실행될 때 사용하는 내부 사양인 `EngineRunSpec`을 정의합니다.

## 1. 개요

`EngineRunSpec`은 워커 래퍼 없이 엔진을 직접 실행하는 데 필요한 최소한의 정보를 담고 있습니다. 엔진은 이 페이로드를 소비하여 실제 작업을 수행합니다.

## 2. 스키마 (Schema)

- `contract_version`: "v1" | "v2"
- `command`: 실행할 명령어 (예: "generate")
- `config_name`: Hydra 설정 이름
- `config_dir`: 설정 디렉토리 경로
- `args`: 명령어별 인자 딕셔너리
- `overrides`: Hydra 오버라이드 리스트
- `runtime`: 실행 환경 설정
  - `mode`: "worker" | "local_debug"
  - `bootstrap_mode`: "auto" | "uv" | "pip"
  - `extras`: 설치할 추가 의존성 리스트
  - `extra_env`: 추가 환경변수

## 3. 책임 소재 (Ownership)

- **엔진 (Engine)**: 명령어/설정/인자 해설, CLI 실행 및 결과 페이로드 생성.
- **워커 래퍼 (Wrapper)**: 리포지토리 URL/참조(Ref), 엔트리포인트, Prefect 제출 및 재시도 로직 관리, artifact 업로드 및 MLflow run linkage 관리.

엔진은 워커가 제공한 런타임 입력만 사용합니다.
- `MLFLOW_TRACKING_URI`는 그대로 사용합니다.
- durable artifact가 있으면 `ORCH_ENGINE_ARTIFACT_DIR` 아래에 파일을 쓰고 `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`를 작성합니다.
- 실행 결과 stdout JSON에는 가능하면 `mlflow_run_id`를 포함해 워커가 후속 run linkage를 수행할 수 있게 합니다.
- MinIO presign, storage-api 호출, MLflow 재조회는 엔진 책임이 아닙니다.

## 4. 호환성

- `v2` 명령어: `generate`, `verify`, `animate`
- `v1` Shim: `gen-verify`, `verify-only`, `replay-eval` 지원 유지.

## 5. 참고 문서
- 외부 오케스트레이터 계약: `docs/contracts/orchestrator.md`
