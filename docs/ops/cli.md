# Discoverex Core CLI Usage Guide

`bin/cli`는 프로젝트 관리, Prefect 운영, 레거시 스크립트 실행을 위한 통합 엔트리포인트입니다. 이 도구는 `scripts/cli/`에 위치한 파이썬 로직을 실행하는 래퍼입니다.

## 1. 기본 명령어 구조

```bash
./bin/cli [OPTIONS] COMMAND [ARGS]...
```

각 명령어 뒤에 `--help`를 붙여 상세 옵션을 확인할 수 있습니다.

## 2. Prefect 관련 명령 (`prefect`)

Prefect flow 및 작업 등록을 관리합니다.

### Flow 배포
브랜치별 엔진 flow를 remote-source Prefect deployment로 등록합니다.
```bash
./bin/cli prefect deployflow generate --branch dev --work-pool-name gpu-pool
```

deployment 이름은 `discoverex-<flow-kind>-<branch>` 규칙을 따릅니다.
등록 시 Prefect는 `prefect_flow.py:<flow-kind-entrypoint>`와 Git source를 사용합니다.
필요하면 `--ref <branch|tag|sha>`로 실행 ref를 이름용 branch와 분리할 수 있습니다.

### 작업 등록 (Registration)
표준 job spec을 브랜치별 deployment에 제출합니다. `--branch`는 필수입니다. 모든 설정은 YAML 형식을 지원합니다.
```bash
./bin/cli prefect registerflow generate --branch dev
```

기본 spec 파일은 `infra/register/job_specs/real-generate-sdxl-gpu-8gb.yaml`입니다.
메모리 압박이 있으면 `infra/register/job_specs/real-generate-sdxl-gpu-8gb-safe.yaml`을 사용해
`sequential` offload와 더 작은 inpaint patch/step 조합으로 제출할 수 있습니다.
기존 `deploy`/`register` 명령은 `combined` 기본 배포를 위한 호환 별칭으로 유지됩니다.

### 배치 등록
여러 scene을 CSV 기준으로 한 번에 제출할 때 사용합니다.
```bash
./bin/cli prefect registerbatch scenes.csv --branch dev
```

### 실험 배포
대량 실험용 deployment는 단발 flow와 별도로 분리합니다.
```bash
./bin/cli prefect deployexperiment --experiment naturalness --branch dev
```

deployment 이름은 `discoverex-<experiment>-experiment-<branch>` 규칙을 따릅니다. 기본 큐는 `gpu-fixed-batch`입니다.

### 실험 스윕 제출
YAML sweep spec 기반으로 실험 잡을 fan-out합니다.
```bash
./bin/cli prefect registerexperimentsweep --experiment naturalness --branch dev
./bin/cli prefect registerexperimentsweep --experiment naturalness --branch dev --sweep-spec infra/register/sweeps/naturalness_medium.yaml
```

실험은 수동 `generate` deployment와 다른 deployment namespace를 사용하므로, 대량 실험이 단발 실행 경로를 덮어쓰지 않습니다.

### 로그 확인
특정 Prefect flow run ID의 로그를 가져옵니다.
```bash
./bin/cli prefect check-logs <FLOW_RUN_ID>
```

## 3. 레거시 명령 (`legacy`)

이전의 쉘 스크립트나 파이썬 스크립트를 통합 실행합니다.

### CPU 생성 (Legacy)
CPU에서 프롬프트 기반 생성을 실행합니다.
```bash
./bin/cli legacy generate-cpu --width 512 --height 384
```

### MinIO 번들 확인
MinIO의 Scene 번들 내용을 검사합니다.
```bash
./bin/cli legacy check-minio --bucket-name scenes --bundle-key path/to/bundle
```

## 엔진 E2E 검증

로컬 검증 하네스는 엔진 CLI로 바로 실행할 수 있습니다.

```bash
uv run discoverex e2e --scenario all
uv run discoverex e2e --scenario live-services --ensure-live-infra
```

로컬 시나리오는 별도 MLflow 서버 없이 `sqlite:///mlflow.db` 기반으로 동작합니다.

## 4. 아키텍처 및 내부 구조

- **엔트리포인트**: `bin/cli` (Bash)
- **명령어 로직**: `scripts/cli/main.py` (Typer)
- **구현 모듈**:
  - `scripts/cli/prefect.py`: Prefect 관련 작업.
  - `scripts/cli/legacy.py`: 레거시 스크립트 통합.
