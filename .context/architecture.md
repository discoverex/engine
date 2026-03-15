# Discoverex Architecture & Module Organization

이 문서는 Discoverex 프로젝트의 아키텍처 설계와 모듈 구성의 기준을 정의합니다.

## 1. 헥사고널 아키텍처 (Hexagonal Layout)

이 프로젝트는 헥사고널 아키텍처를 따르며, 도메인 로직과 외부 어댑터를 명확히 분리합니다.

- `src/discoverex/domain`: 캐논 DTO, 불변식, 도메인 서비스 (SSOT)
- `src/discoverex/application/ports`: 모델/스토리지/트래킹/IO/리포팅 인터페이스
- `src/discoverex/application/use_cases`: 파이프라인 오케스트레이션 로직 (`generate`, `verify`, `animate`)
- `src/discoverex/adapters/inbound/cli`: Typer CLI 진입점 (`discoverex`)
- `src/discoverex/adapters/outbound`: 외부 연동 구현체 (HF 모델, MinIO, MLflow 등)
- `src/discoverex/bootstrap`: Hydra 설정을 기반으로 애플리케이션 컨텍스트 조립 (Composition Root)

## 2. 핵심 원칙

- **Scene 중심**: Scene이 시스템의 루트 엔티티이며 모든 파이프라인의 기준입니다.
- **포트 의존성**: 유스케이스는 포트 인터페이스에만 의존하며, 구체적인 어댑터 구현을 직접 참조하지 않습니다.
- **설정 기반 조립**: Hydra 설정을 통해 실행 시점에 어댑터를 동적으로 교체합니다.
- **불변성 유지**: 도메인 객체는 불변식을 유지하며, 어댑터는 캐논 세만틱을 변경할 수 없습니다.

## 3. 모듈 및 레이어링 가이드

- **파일당 단일 책임**: 각 파일은 하나의 책임만 가지며, 200라인 이하 유지를 권장합니다.
- **캡슐화**: `__init__.py`를 적극 활용하여 패키지 내부를 캡슐화하고 안정적인 임포트 경로를 제공합니다.
- **어댑터 분리**: 외부 라이브러리(Transformers, PyTorch 등) 의존성은 반드시 `adapters/outbound` 내부의 특정 어댑터에만 국한시킵니다.

## 4. 제거된 레거시 레이어 (Hard-cut)

아래 레이어들은 더 이상 사용되지 않으며, 새로운 구조로 대체되었습니다.
- `src/discoverex/pipelines`
- `src/discoverex/cli` -> `adapters/inbound/cli`로 이동
- `src/discoverex/generation`
- `src/discoverex/verification`
- `src/discoverex/ux`
- `src/discoverex/storage`
- `src/discoverex/tracking`

## 5. 설정 구조 (Hydra)

`conf/` 디렉토리는 어댑터와 모델의 조립 방식을 정의합니다.
- `conf/models/`: 모델 어댑터 설정 (hidden_region, inpaint, perception, fx)
- `conf/adapters/`: 인프라 어댑터 설정 (artifact_store, metadata_store, tracker)
- `conf/*.yaml`: 실행 파이프라인별 기본 설정 조합
