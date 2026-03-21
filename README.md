# Discoverex Core Engine

Discoverex Core 엔진 리포지토리입니다. Scene Canonical 규약을 중심으로 `generate`, `verify`, `animate` 파이프라인을 실행합니다.

## 1. 핵심 원칙 및 아키텍처
- **도메인 중심 설계**: Scene이 시스템의 루트 엔티티입니다.
- **헥사고널 아키텍처**: 비즈니스 로직과 외부 어댑터(ML, Storage, Tracker)를 엄격히 분리합니다.
- **설정 기반 조립**: Hydra 설정을 통해 실행 시점에 어댑터를 동적으로 교환합니다.
- **워커 계약 우선**: 워커는 `MLFLOW_TRACKING_URI`와 engine artifact 디렉터리/manifest 경로를 주입하고, 업로드와 MLflow URI tag 기록은 워커가 담당합니다.

## 2. 현재 플로우 구조

### 공식 Prefect 엔트리포인트
- `discoverex-engine-flow`: 일반 JobSpec 진입점
- `discoverex-generate-flow`: generate 전용 진입점
- `discoverex-verify-flow`: verify 전용 진입점
- `discoverex-animate-flow`: animate 전용 진입점
- `discoverex-combined-flow`: 명시적 복합 실행 경로

### 내부 엔진 플로우
- `discoverex-engine-entry-pipeline`: settings/snapshot 생성과 subflow dispatch
- `discoverex-generate-pipeline`: scene 생성 및 검증 포함 메인 생성 파이프라인
- `discoverex-verify-pipeline`: 기존 scene 검증 파이프라인
- `discoverex-generate-inpaint-variant-pack`: variant pack 생성 파이프라인

### 호환/서브플로우 핸들러
- generate 계열: `generate_v1_compat`, `generate_v2_compat`, `generate_verify_v2`, `generate_object_only`, `generate_inpaint_variant_pack`
- verify 계열: `verify_v1_compat`
- animate 계열: `animate_replay_eval`, `animate_stub`

## 3. 문서 가이드 (Documentation Index)

프로젝트에 대한 자세한 내용은 아래 문서를 참고하십시오.

### **Core & Specification (기술 명세)**
- [Architecture & Module Organization](.context/architecture.md): 프로젝트 구조 및 아키텍처 원칙.
- [Scene Canonical Spec v1](.context/canon.md): Scene 데이터 규약 (SSOT).
- [Current Capabilities & Specs](.context/capabilities.md): 현재 엔진의 실행 능력 및 제약 사항.

### **Operations (운영 및 실행)**
- [CLI Usage Guide](docs/ops/cli.md): 통합 CLI 명령어 사용법.
- [Runtime & Operations Guide](docs/ops/runtime.md): 로컬/워커 모드 설정 및 실행 가이드.

### **Development (개발 및 마이그레이션)**
- [Pipeline Adapter Guide](docs/dev/adapters.md): 신규 어댑터(모델/스토리지 등) 추가 방법.
- [Prefect Migration History](docs/dev/prefect-migration.md): Prefect 마이그레이션 진행 상태 및 히스토리.
- [HANDOFF](docs/dev/handoff.md): 현재 개발 상태 및 후속 작업 체크리스트.

### **Contracts (인터페이스 및 계약)**
- [Engine Run Contract](docs/contracts/engine-run.md): 엔진 내부 실행 사양.
- [Orchestrator & Worker Contract](docs/contracts/orchestrator.md): 외부 Prefect/워커 실행 계약.
- [Registration Details](docs/contracts/registration/README.md): Prefect 등록 관련 세부 사양.

## 4. 퀵스타트 (Quick Start)

```bash
# 환경 설정
just sync

# 로컬 생성 실행
just run discoverex generate --background-asset-ref bg://dummy

# 특정 프로필(CPU) 실행
uv run discoverex generate --background-asset-ref bg://dummy -o profile=cpu_fast
```

## 5. 품질 검증
```bash
just lint
just typecheck
just test
```
