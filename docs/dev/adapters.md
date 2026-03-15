# Pipeline Adapter Guide

이 문서는 `discoverex`에서 새로운 모델, 인프라 어댑터, 그리고 설정을 추가하고 교체하는 방법을 설명합니다.

## 1. 개요

Discoverex는 헥사고널 아키텍처를 기반으로 하며, 포트(Port) 인터페이스를 구현한 어댑터(Adapter)를 Hydra 설정을 통해 조립합니다. 코드 수정 없이 설정을 통해 아래의 항목을 교체할 수 있습니다.

- **모델 어댑터**: `hidden_region`, `inpaint`, `perception`, `fx`
- **인프라 어댑터**: `artifact_store`, `metadata_store`, `tracker`, `scene_io`, `report_writer`

## 2. 신규 어댑터 구현 절차

### 1단계: 포트 인터페이스 확인
- 모델 포트: `src/discoverex/application/ports/models.py`
- 스토리지 포트: `src/discoverex/application/ports/storage.py`
- 트래킹 포트: `src/discoverex/application/ports/tracking.py`

### 2단계: 어댑터 클래스 구현
- 위치: `src/discoverex/adapters/outbound/<group>/my_adapter.py`
- 규칙: 유스케이스에서 직접 어댑터 클래스를 임포트하지 마십시오.

### 3단계: Hydra 설정 등록
- 파일: `conf/<models|adapters>/<group>/my_adapter.yaml`
- 내용: Hydra의 `_target_` 필드에 구현한 클래스의 정규 경로를 지정합니다.

```yaml
# @package adapters.tracker
_target_: discoverex.adapters.outbound.tracking.my_adapter.MyTrackerAdapter
```

### 4단계: 설정 적용 및 실행
- 실행 시 `-o` 또는 `--override` 옵션을 통해 새로운 어댑터를 선택합니다.

```bash
uv run discoverex generate -o adapters/tracker=my_tracker
```

## 3. 프로필(Profile) 활용

자주 사용되는 어댑터와 설정의 조합을 프로필로 관리할 수 있습니다. 예를 들어, `profile=cpu_fast`는 CPU 추론 전용 모델들과 빠른 추론 옵션을 한 번에 적용합니다.

## 4. 참고 문서
- 아키텍처 원칙: `.context/architecture.md`
- 로컬/워커 실행 모드: `docs/ops/runtime.md`
