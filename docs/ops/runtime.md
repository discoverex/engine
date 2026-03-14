# Discoverex Runtime & Operations Guide

Discoverex 엔진의 로컬/워커 실행 모드와 실제 파이프라인 운영 절차를 설명합니다.

## 1. 핵심 개념 (Unified Commands)

모든 파이프라인은 동일한 엔진(`discoverex`) 명령어로 실행됩니다. 환경에 따른 차이는 Hydra 어댑터 선택과 환경변수 주입을 통해 해결합니다.

**표준 명령어 (v2):**
- `generate`: 씬 생성 및 조립
- `verify`: 기존 씬 검증
- `animate`: (현재 stub) 애니메이션 생성

**레거시 명령어 (v1 Shim):**
- `gen-verify` -> `generate`
- `verify-only` -> `verify`
- `replay-eval` -> `animate`
*(실행 시 Deprecation 경고가 출력됩니다)*

## 2. 실행 모드 정의

### 2.1 Local Mode (로컬 개발용)
- **저장소**: 로컬 파일 시스템 (`adapters/artifact_store=local`)
- **트래커**: 로컬 MLflow (`adapters/tracker=mlflow_local`)
- **설정**: 별도 서버 없이 `sqlite:///mlflow.db`와 `artifacts/`를 로컬에 생성합니다.

### 2.2 Worker Mode (운영/스케줄러용)
- **트래커**: 워커가 주입한 `MLFLOW_TRACKING_URI`를 그대로 사용합니다.
- **산출물**: 엔진은 `ORCH_ENGINE_ARTIFACT_DIR`와 `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`를 사용해 결과 파일과 manifest를 남깁니다.
- **업로드 책임**: MinIO 업로드, presign 요청, MLflow artifact URI tag 기록은 워커가 담당합니다.
- **인증**: 원격 MLflow가 보호되어 있으면 워커가 프록시를 띄우고 엔진에는 치환된 URI만 전달합니다.

## 3. 실제 실행 예시

### 로컬 모드 기본 실행 (just 사용 권장)
```bash
just sync
just run discoverex generate --background-asset-ref bg://dummy
```

### 로컬 모드 CPU 실행 (profile 사용)
```bash
uv run discoverex generate --background-asset-ref bg://dummy -o profile=cpu_fast
```

### 워커 모드 수동 디버그 실행
```bash
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
ORCH_ENGINE_ARTIFACT_DIR="$PWD/.tmp/engine-artifacts" \
ORCH_ENGINE_ARTIFACT_MANIFEST_PATH="$PWD/.tmp/engine-artifacts.json" \
uv run discoverex generate \
  --background-asset-ref bg://dummy \
  -o adapters/tracker=mlflow_server
```

이 예시는 워커가 실제로 주입하는 계약을 로컬에서 흉내 내는 디버그 예시입니다.

## 4. 필수 환경변수 및 가드레일

워커 환경에서 실행 시 아래 환경변수가 필수적으로 관리되어야 합니다.
- `MLFLOW_TRACKING_URI`: MLflow 서버 주소 또는 워커 프록시 주소
- `ORCH_ENGINE_ARTIFACT_DIR`: 워커가 만든 엔진 산출물 디렉터리
- `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`: 엔진 manifest 파일 경로

**운영 원칙:**
1. 엔진은 `MLFLOW_TRACKING_URI`를 그대로 사용하고, 워커가 후속 MLflow linkage를 담당합니다.
2. durable output은 worker-managed artifact directory 계약으로만 보장됩니다.
3. 실행 후 산출물 영속화는 worker upload 결과와 manifest를 기준으로 확인합니다.

## 5. 트러블슈팅 (Quick Fix)

- **Hydra Target 에러**: `conf/models/*` 또는 `conf/adapters/*`의 `_target_` 경로를 확인하십시오.
- **Tracker 초기화 에러**: `uv sync --extra tracking`이 실행되었는지 확인하십시오.
- **Worker artifact 업로드 에러**: `ORCH_ENGINE_ARTIFACT_DIR`와 `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH`가 주입되었는지, manifest 경로와 상대경로가 계약에 맞는지 확인하십시오.

## 6. 로컬 E2E 검증

엔진 실행 계약을 한 번에 확인하려면 아래 하네스를 사용합니다.

```bash
UV_CACHE_DIR="$PWD/.cache/uv" uv run python infra/e2e/engine_runtime_e2e.py --scenario all
```

이 스크립트는 두 경로를 검증합니다.
- `tracking-artifact`: tiny runtime으로 실제 generate 실행, 엔진의 MLflow 기록 경계 확인
- `worker-contract`: worker artifact 디렉토리/manifest/output upload 계약 확인

## 7. 참고 문서
- CLI 상세 옵션: `docs/ops/cli.md`
- 마이그레이션 이력: `docs/dev/prefect-migration.md`
