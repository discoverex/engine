# Discoverex Engine - 디렉토리 구조 문서

> 생성일: 2026-03-03
> 대상 경로: `/home/user/discoverex/engine`

---

## 최상위 구조

```
engine/
├── src/discoverex/          # 핵심 소스 코드 (Hexagonal Architecture)
├── delivery/                # 프론트엔드 번들 변환 레이어
├── conf/                    # Hydra 설정 파일
├── tests/                   # 단위/통합 테스트
├── orchestrator/            # Prefect 워크플로우 래퍼
├── infra/                   # 인프라 구성 (Docker Compose)
├── docs/                    # 프로젝트 문서
├── scripts/                 # 유틸리티 스크립트
├── .context/                # 아키텍처 핸드오프 문서
├── .devcontainer/           # VSCode 개발 컨테이너 설정
├── .github/workflows/       # CI/CD 파이프라인
├── main.py                  # CLI 진입점 래퍼
├── pyproject.toml           # UV 프로젝트 설정 / 의존성 정의
└── Makefile                 # 빌드 자동화 (sync, test, lint, typecheck, run)
```

---

## 소스 코드 계층 (`src/discoverex/`)

### 도메인 레이어 - `domain/`
비즈니스 엔티티와 규칙의 핵심. 프레임워크 의존성 없음.

| 파일 | 설명 |
|------|------|
| `scene.py` | 루트 엔티티: `Scene`, `SceneMeta`, `Background`, `Composite`, `Answer`, `Difficulty`, `ObjectGroup`. answer region ID 존재 검증 포함 |
| `region.py` | `Region` 엔티티: `Geometry`(BBOX + mask_ref), `RegionRole`(candidate/distractor/answer/object), `RegionSource`(candidate_model/inpaint/fx/manual) |
| `goal.py` | `Goal`: `GoalType`(relation/count/shape/semantic), `AnswerForm`(region_select/click_one/click_multiple), 제약 구조 |
| `verification.py` | `VerificationResult`(score+pass+signals), `FinalVerification`(total_score+pass+reason), `VerificationBundle`(logical+perception+final) |
| `services/verification.py` | 도메인 서비스: `run_logical_verification()`, `integrate_verification()`, **`resolve_answer()`**, **`compute_difficulty()`**, **`compute_scene_difficulty()`**, **`integrate_verification_v2()`** — Validator Phase 4 순수 수식 포함 |
| `services/judgement.py` | 판정 도메인 서비스 |

### 애플리케이션 레이어 - `application/`
유스케이스 조율 및 포트(인터페이스) 정의.

#### 포트 (Hexagonal 경계 인터페이스) - `application/ports/`

| 파일 | 프로토콜 | 설명 |
|------|----------|------|
| `models.py` | `HiddenRegionPort`, `InpaintPort`, `PerceptionPort`, `FxPort` (기존 load/predict 패턴) + **`PhysicalExtractionPort`**, **`LogicalExtractionPort`**, **`VisualVerificationPort`** (Validator load/extract\|verify/unload 패턴) |
| `storage.py` | `ArtifactStorePort`, `MetadataStorePort` | 아티팩트 및 메타데이터 저장소 추상화 |
| `tracking.py` | `TrackerPort` | MLflow 실험 추적 추상화 |
| `io.py` | `SceneIOPort` | Scene JSON 입출력 추상화 |
| `reporting.py` | `ReportWriterPort` | 리포트 생성 추상화 |

#### 유스케이스 - `application/use_cases/`

| 파일 | 설명 |
|------|------|
| `gen_verify/orchestrator.py` | 메인 오케스트레이터: 배경→영역→검증→패키징 |
| `gen_verify/scene_builder.py` | 파이프라인 출력으로부터 Scene 엔티티 빌드 |
| `gen_verify/region_pipeline.py` | 숨은 영역 감지 + 인페인팅 파이프라인 |
| `gen_verify/verification_pipeline.py` | 논리적 + 지각적 검증 |
| `gen_verify/composite_pipeline.py` | 최종 이미지 합성 |
| `gen_verify/persistence.py` | Scene 저장 + 메타데이터 업데이트 |
| `gen_verify/types.py` | 파이프라인 내부 데이터 타입 |
| `verify_only.py` | 기존 Scene 재검증 |
| `replay_eval.py` | 다수 Scene 일괄 평가 |
| **`validator/__init__.py`** | **ValidatorOrchestrator, run_validator export** |
| **`validator/orchestrator.py`** | **4단계 순차 파이프라인 오케스트레이터 (VRAM 바톤 터치 전략, try/finally 보장)** |

### 어댑터 레이어 - `adapters/`

#### 인바운드 - `adapters/inbound/cli/`
**main.py (Typer CLI):** 4개 명령어
- `gen-verify --background-asset-ref` → 생성 + 검증 실행
- `verify-only --scene-json` → 저장된 Scene 재검증
- `replay-eval --scene-jsons` → 일괄 평가
- **`validate --composite-image --object-layer` → Validator 파이프라인 실행 (JSON 결과 출력)**

#### 아웃바운드 - `adapters/outbound/`

**모델 어댑터:**
| 파일 | 설명 |
|------|------|
| `dummy.py` | 테스트용 목(Mock) 모델 — 기존 4종 + **`DummyPhysicalExtraction`, `DummyLogicalExtraction`, `DummyVisualVerification`** |
| `hf_*.py` | HuggingFace Transformers 구현체 (fx, hidden_region, inpaint, perception) |
| **`hf_mobilesam.py`** | **Phase 1: MobileSAM 기반 물리 메타데이터 추출 (occlusion, z_index, z_depth_hop BFS, cluster_density, euclidean_distance)** |
| **`hf_moondream2.py`** | **Phase 2: Moondream2 4-bit VLM 기반 논리 관계 추출 (encode_image → NetworkX graph → degree/hop/diameter)** |
| **`hf_yolo_clip.py`** | **Phase 3: YOLOv10-N + CLIP 병렬 로드 (IoU 기반 sigma_threshold, bbox-crop per-object DRR)** |
| `tiny_hf_*.py` | 경량 HuggingFace 변형 |
| `tiny_torch_*.py` | 경량 PyTorch 변형 |
| `runtime.py` | 디바이스/dtype/배치 관리 |
| `fx_artifact.py` | FX 출력 아티팩트 처리 |

**저장소 어댑터:**
| 파일 | 설명 |
|------|------|
| `storage/artifact.py` | `LocalArtifactStoreAdapter` (JSON to 디스크) + `MinioArtifactStoreAdapter` (S3 호환, boto3) |
| `storage/metadata.py` | `LocalMetadataStoreAdapter` (JSON 인덱스) + `PostgresMetadataStoreAdapter` |

**기타 아웃바운드:**
| 파일 | 설명 |
|------|------|
| `tracking/mlflow.py` | MLflow 실험 추적 어댑터 |
| `io/json_scene.py` | JSON Scene 로더/세이버 |
| `reports/reports.py` | 리포트 작성 구현체 |

### 부트스트랩 (Composition Root) - `bootstrap/`

| 파일 | 설명 |
|------|------|
| `container.py` | 구체 어댑터 인스턴스화 |
| `factory.py` | `build_context()` — Hydra 기반 DI 컨테이너 구성 + **`build_validator_context()`** — ValidatorPipelineConfig → ValidatorOrchestrator 직접 생성 |
| `context.py` | `AppContext` 구체 데이터클래스 (`AppContextLike` 프로토콜 구현) |
| `config_defaults.py` | 설정 해석 로직 |

### 설정 스키마 - `config/`

| 파일 | 설명 |
|------|------|
| `schema.py` | Pydantic 설정 모델: `ModelsConfig`, `AdaptersConfig`, `RuntimeModelConfig`, `RuntimeEnvConfig`, `ThresholdsConfig`, `ModelVersionsConfig`, `PipelineConfig` + **`ValidatorModelsConfig`, `ValidatorThresholdsConfig`, `ValidatorPipelineConfig`** (PipelineConfig와 독립, extra="forbid") |
| `config_loader.py` | `load_pipeline_config()` — Hydra + OmegaConf → Pydantic 검증 + **`load_validator_config()`** — ValidatorPipelineConfig 반환 |

### 모델 타입 - `models/`

| 파일 | 설명 |
|------|------|
| `types.py` | `ModelHandle`, `HiddenRegionRequest`, `InpaintRequest`, `PerceptionRequest`, `FxRequest`, `FxPrediction` + **`PhysicalMetadata`, `LogicalStructure`, `VisualVerification`, `ValidatorInput`** (Validator Phase 1~4 I/O 타입) |

---

## 설정 파일 (`conf/`)

```
conf/
├── gen_verify.yaml          # gen-verify 파이프라인 기본 설정
├── verify_only.yaml         # verify-only 기본 설정
├── replay_eval.yaml         # replay-eval 기본 설정
├── validator.yaml           # [NEW] Validator 파이프라인 Hydra 진입점
├── models/
│   ├── hidden_region/       # dummy, hf, tiny_hf, tiny_torch
│   ├── inpaint/             # dummy, hf, tiny_hf, tiny_torch
│   ├── perception/          # dummy, hf, tiny_hf, tiny_torch
│   ├── fx/                  # dummy, hf, tiny_hf, tiny_torch
│   ├── physical_extraction/ # [NEW] mobilesam.yaml, dummy.yaml
│   ├── logical_extraction/  # [NEW] moondream2.yaml, dummy.yaml
│   └── visual_verification/ # [NEW] yolo_clip.yaml, dummy.yaml
├── adapters/
│   ├── artifact_store/      # local.yaml, minio.yaml
│   ├── metadata_store/      # local_json.yaml, postgres.yaml
│   ├── tracker/             # mlflow_file.yaml, mlflow_server.yaml
│   ├── scene_io/            # json.yaml
│   └── report_writer/       # local_json.yaml
└── runtime/
    ├── model_runtime/       # cpu.yaml, gpu.yaml
    └── env/                 # default.yaml
```

---

## 딜리버리 레이어 (`delivery/spot_the_hidden/`)

프론트엔드 번들 생성을 위한 별도 패키지.

| 파일 | 설명 |
|------|------|
| `schema.py` | `GameBundle` = Scene 참조 + `PlayableScene`(이미지, 목표, 힌트, UI 플래그) + `AnswerKey`(정답 region IDs) + `DeliveryMeta`(저장 타입, 이미지 해시, 상태, 난이도) |
| `cli.py` | Scene JSON → GameBundle JSON 변환 CLI |
| `converter.py` | `Scene` → `GameBundle` 변환 로직 |
| `io.py` | GameBundle I/O 작업 |
| `README.md` | 딜리버리 패키지 문서 |

---

## 테스트 (`tests/`)

| 파일 | 설명 |
|------|------|
| `test_config_schema.py` | 설정 스키마 검증 |
| `test_config_tracking_uri.py` | 추적 URI 설정 |
| `test_architecture_constraints.py` | Hexagonal 경계 강제 |
| `test_model_ports_contract.py` | 모델 포트 인터페이스 계약 |
| `test_hexagonal_boundaries.py` | 어댑터 임포트 제한 검증 |
| `test_fx_output_artifact.py` | FX 아티팩트 처리 |
| `test_fx_prediction_contract.py` | FX 예측 인터페이스 |
| `test_tiny_model_pipeline_smoke.py` | E2E 스모크 테스트 |
| `test_gen_verify_composite.py` | gen-verify 합성 |
| `test_artifact_verification_consistency.py` | 아티팩트 일관성 |
| **`test_validator_pipeline_smoke.py`** | **Dummy 어댑터 기반 Validator E2E 스모크 테스트 (5개)** |
| **`test_validator_scoring.py`** | **Phase 4 순수 수식 단위 테스트 (21개): resolve_answer, compute_difficulty, compute_scene_difficulty, integrate_verification_v2** |
| `delivery/test_schema_validation.py` | 딜리버리 번들 스키마 |
| `delivery/test_converter_mapping.py` | Scene→Bundle 변환 |
| `delivery/test_scene_to_bundle_artifact.py` | 번들 아티팩트 생성 |
| `delivery/test_front_payload_strips_answer_key.py` | 정답키 제거 검증 |

---

## 오케스트레이터 (`orchestrator/`)

| 파일 | 설명 |
|------|------|
| `prefect_flows.py` | Prefect 플로우 래퍼: `gen_verify_flow()`(재시도 2회, 3초 딜레이), `verify_only_flow()`, `replay_eval_flow()` |

---

## 인프라 (`infra/`)

| 파일 | 설명 |
|------|------|
| `docker-compose.yml` | 서비스: PostgreSQL + MinIO + MLflow (+ 선택적 Airflow 프로파일) |

---

## 문서 (`docs/`)

```
docs/
├── pipeline-adapter-guide.md   # 신규 모델/저장소/추적 어댑터 추가 가이드
├── handheld-ops-card.md        # 운영 빠른 참조
├── execution-contract.md       # 파이프라인 실행 보장 사항
└── Validator/
    ├── instruction_1.md        # Validator 파이프라인 설계 명세 (4단계 연쇄 추출)
    ├── DIR.md                  # 현재 파일 - 디렉토리 구조 문서
    └── plan_pipeline.md        # Validator 파이프라인 구현 계획
```

---

## 컨텍스트 문서 (`.context/`)

| 파일 | 설명 |
|------|------|
| `overview.md` | 프로젝트 아키텍처 및 핸드오프 가이드 |
| `HANDOFF.md` | 검증된 실행 상태 포함 핸드오프 문서 |
| `canon.md` | 표준 Scene 계약 참조 |
| `git-conventions.md` | Git 워크플로우 (브랜치 명명, 커밋 접두사) |

---

## 핵심 의존성

| 그룹 | 패키지 |
|------|--------|
| Core | `pydantic>=2.12.5`, `typer>=0.24.1`, `hydra-core>=1.3.2` |
| Orchestration | `prefect>=3.6.20` |
| Tracking | `mlflow>=3.10.0` |
| Storage | `boto3`, `psycopg[binary]`, `sqlalchemy` |
| ML CPU | `torch`, `transformers` |
| ML GPU | `torch`, `transformers`, `accelerate` |
| **Validator** | **`mobile-sam>=1.0.0`, `ultralytics>=8.0.0`, `bitsandbytes>=0.41.0`, `networkx>=3.0`, `pillow>=11.3.0`, `numpy>=1.26.0`** |
| Dev | `mypy`, `pytest`, `ruff`, `pyyaml` |

---

## Validator 파이프라인 대상 모델 (instruction_1.md 기준)

| Phase | 모델 | VRAM 전략 | 출력 |
|-------|------|-----------|------|
| Phase 1 | MobileSAM | 단독 로드 → 해제 | `physical_metadata.json` |
| Phase 2 | Moondream2 (4-bit) | 단독 로드 → 해제 | `logical_structure.json` |
| Phase 3 | YOLOv10-N + CLIP | 병렬 로드 (4GB 미만) | `visual_verification.json` |
| Phase 4 | 없음 (순수 연산) | VRAM 불필요 | `scene.json` (CANON) |

---

## 데이터 플로우 아키텍처

```
배경 이미지 + 오브젝트 레이어
        │
        ▼
[Phase 1] MobileSAM - 물리 메타데이터 추출
        │ physical_metadata.json
        ▼
[Phase 2] Moondream2 - 논리 관계 추출 (Scene Graph)
        │ logical_structure.json
        ▼
[Phase 3] YOLOv10-N + CLIP - 시각적 난이도 검증
        │ visual_verification.json
        ▼
[Phase 4] 순수 연산 - 정답 판정 + CANON 조립
        │ scene.json
        ▼
Delivery CLI → 백엔드 전송
```
