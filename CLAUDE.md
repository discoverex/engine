# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Discoverex Core Engine — Scene Canonical 규약 중심의 퍼즐 생성(generate), 검증(verify), 애니메이션(animate) 파이프라인 시스템. Python 3.11+, 헥사고널 아키텍처.

## Common Commands

```bash
# 의존성 설치
just sync                    # uv sync --extra tracking

# 품질 검증 (CI와 동일)
just lint                    # ruff check
just format                  # ruff format
just typecheck               # mypy src tests
just test                    # pytest tests/
just check                   # lint + typecheck + test 전체

# 단일 테스트 실행
just test tests/test_foo.py
just test "tests/test_foo.py::test_bar"

# 로컬 파이프라인 실행
just run discoverex generate --background-asset-ref bg://dummy
just run discoverex verify --scene-json <path>

# ML 모델 스모크 테스트 (ml-cpu extra 필요)
just smoke-torch
just smoke-hf
```

린터/타입체커 설정: `pyproject.toml` — ruff(line-length 88, rules E/F/I/B/UP), mypy(strict mode).

## Architecture

**헥사고널 아키텍처 (Ports & Adapters)**로 구성. Scene이 루트 엔티티.

```
src/discoverex/
├── domain/          # 불변 엔티티 (Scene, Region, Verification), 도메인 서비스
├── application/
│   ├── ports/       # 추상 인터페이스 (Model, Storage, Tracking, IO, Reporting)
│   ├── use_cases/   # 파이프라인 오케스트레이션 (gen_verify, validator)
│   ├── flows/       # 엔진 flow 진입점
│   ├── services/    # 애플리케이션 레벨 서비스
│   └── contracts/   # 실행 계약 명세
├── adapters/
│   ├── inbound/cli/ # Typer CLI 진입점
│   └── outbound/    # 구체 구현 (HF 모델, MinIO, MLflow 등)
├── bootstrap/       # Hydra 기반 Composition Root (설정 → 어댑터 조립)
└── config_loader.py
```

**핵심 규칙**:
- 유스케이스는 포트 인터페이스에만 의존, 구체 어댑터 직접 참조 금지
- 외부 라이브러리(Torch, Transformers 등) 의존성은 `adapters/outbound` 내부에만 국한
- 도메인 객체는 불변, 어댑터가 캐논 시맨틱을 변경할 수 없음
- 파일당 단일 책임, 200라인 이하 권장

**설정**: Hydra 기반. `conf/` 디렉토리에서 모델(`conf/models/`), 어댑터(`conf/adapters/`), 프로필(`conf/profile/`) 설정 조합. `-o` 플래그로 런타임 어댑터 교체 가능.

## Execution Modes

- **로컬 모드**: SQLite MLflow, 로컬 파일시스템 아티팩트
- **워커 모드** (Prefect): 환경변수 `MLFLOW_TRACKING_URI`, `ORCH_ENGINE_ARTIFACT_DIR`, `ORCH_ENGINE_ARTIFACT_MANIFEST_PATH` 주입. 엔진은 아티팩트 디렉토리에 파일만 기록하고, 업로드/태깅은 워커가 담당

Prefect flow 진입점: `prefect_flow.py` (루트). 배포 등록: `./bin/cli prefect deploy-flow <flow-kind> --branch <branch>`

## Key Specs

- `.context/canon.md` — Scene Canonical Spec v1 (데이터 모델 SSOT)
- `.context/architecture.md` — 아키텍처 원칙 및 모듈 구성
- `docs/contracts/orchestrator.md` — Prefect/워커 실행 계약
