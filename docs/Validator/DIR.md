# Discoverex Engine - 디렉토리 구조 문서

> 생성일: 2026-03-03 / 최종 수정: 2026-03-11 (occlusion 제거, integrate_verification_v2 9항 반영, Moondream2 degree_map 실계산, max_combined 정규화 개선)
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
| `services/verification.py` | 도메인 서비스: **`ScoringWeights`**(perception 6항 + logical 3항 + difficulty 9항), **`resolve_answer()`**(9조건 체계), **`compute_scene_difficulty()`**(9항 가중 합산), **`integrate_verification_v2()`**(시각 6항 perception + 물리·논리 3항 logical), **`compute_visual_similarity()`**(Lab+Hu 앙상블) |
| `services/judgement.py` | 판정 도메인 서비스 |

### 애플리케이션 레이어 - `application/`
유스케이스 조율 및 포트(인터페이스) 정의.

#### 포트 (Hexagonal 경계 인터페이스) - `application/ports/`

| 파일 | 프로토콜 | 설명 |
|------|----------|------|
| `models.py` | `HiddenRegionPort`, `InpaintPort`, `PerceptionPort`, `FxPort` (기존 load/predict 패턴) + **`PhysicalExtractionPort`**, **`ColorEdgeExtractionPort`** (신규), **`LogicalExtractionPort`**, **`VisualVerificationPort`** (Validator load/extract\|verify/unload 패턴) + **`BundleStorePort`** |
| `storage.py` | `ArtifactStorePort`, `MetadataStorePort` |
| `tracking.py` | `TrackerPort` |
| `io.py` | `SceneIOPort` |
| `reporting.py` | `ReportWriterPort` |

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
| **`validator/orchestrator.py`** | **5-Phase 순차 파이프라인 오케스트레이터 (VRAM 바통 터치 전략, try/finally 보장)** |
| **`validator/scoring.py`** | **Phase 5 순수 계산: visual_degree(alpha_degree_map)/logical_degree(scene graph degree_map) 분리, degree_norm = (visual+logical)/max_combined 복합 계산 (max_combined = max_visual + max_logical), VerificationBundle 생성** |

### 어댑터 레이어 - `adapters/`

#### 인바운드 - `adapters/inbound/cli/`
**main.py (Typer CLI):** 4개 명령어
- `generate --background-asset-ref` → 생성 + 검증 실행
- `verify --scene-json` → 저장된 Scene 재검증
- `animate --scene-jsons` → 현재 stub (미구현)
- **`validate --composite-image --object-layer` → Validator 파이프라인 실행 (JSON 결과 출력)**

#### 아웃바운드 - `adapters/outbound/`

**모델 어댑터:**
| 파일 | 설명 |
|------|------|
| `dummy.py` | 테스트용 목(Mock) 모델 — 기존 4종 + **`DummyPhysicalExtraction`**, **`DummyColorEdgeExtraction`** (신규), **`DummyLogicalExtraction`**, **`DummyVisualVerification`** |
| `hf_*.py` | HuggingFace Transformers 구현체 (fx, hidden_region, inpaint, perception) |
| **`hf_mobilesam.py`** | **Phase 1: MobileSAM 기반 물리 메타데이터 추출 (z_index, z_depth_hop BFS, cluster_density, euclidean_distance, alpha_degree_map). occlusion_map 제거됨.** |
| **`cv_color_edge.py`** | **Phase 2: OpenCV 기반 Color&Edge 추출 — CIE-Lab 색상 대비, Canny 경계 강도, obj_color_map, hu_moments_map. `compute_visual_similarity()` 포함 (Lab+Hu 0.5:0.5 앙상블). CPU 전용, torch 불필요.** |
| **`hf_moondream2.py`** | **Phase 3: Moondream2 4-bit VLM 기반 논리 관계 추출 (encode_image → NetworkX graph → degree_map(undirected degree 실계산)/hop_map/diameter). degree_map = logical_degree 소스 (visual_degree의 alpha_degree_map과 별개)** |
| **`hf_yolo_clip.py`** | **Phase 4: YOLOv10-N + CLIP 병렬 로드 (IoU 기반 sigma_threshold, bbox-crop per-object `drr_slope` — log(σ) 대비 유사도 감소 기울기, np.polyfit. similar_count/distance는 Phase 2 결과로 실계산)** |
| `tiny_hf_*.py` | 경량 HuggingFace 변형 |
| `tiny_torch_*.py` | 경량 PyTorch 변형 |
| `runtime.py` | 디바이스/dtype/배치 관리 |
| `fx_artifact.py` | FX 출력 아티팩트 처리 |
| **`bundle_store.py`** | **`LocalJsonBundleStore` — VerificationBundle을 JSON 파일로 영속화 (BundleStorePort 구현체)** |

**저장소 어댑터:**
| 파일 | 설명 |
|------|------|
| `storage/artifact.py` | `LocalArtifactStoreAdapter` + `MinioArtifactStoreAdapter` |
| `storage/metadata.py` | `LocalMetadataStoreAdapter` + `PostgresMetadataStoreAdapter` |

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
| `factory.py` | `build_context()` — Hydra 기반 DI 컨테이너 구성 + **`build_validator_context()`** |
| `context.py` | `AppContext` 구체 데이터클래스 |
| `config_defaults.py` | 설정 해석 로직 |

### 설정 스키마 - `config/`

| 파일 | 설명 |
|------|------|
| `schema.py` | Pydantic 설정 모델: `ModelsConfig`, `AdaptersConfig` 등 + **`ValidatorModelsConfig`**, **`ValidatorThresholdsConfig`**, **`ValidatorPipelineConfig`** |
| `config_loader.py` | `load_pipeline_config()` + **`load_validator_config()`** |

### 모델 타입 - `models/`

| 파일 | 설명 |
|------|------|
| `types.py` | `ModelHandle`, `HiddenRegionRequest`, `InpaintRequest`, `PerceptionRequest`, `FxRequest`, `FxPrediction` + **`PhysicalMetadata`** (z_depth_hop_map, cluster_density_map, alpha_degree_map — `occlusion_map` 제거), **`ColorEdgeMetadata`** (color_contrast_map, edge_strength_map, obj_color_map, hu_moments_map), **`LogicalStructure`**, **`VisualVerification`** (drr_slope_map, similar_count_map, similar_distance_map), **`ValidatorInput`** |

---

## 학습 파이프라인 (`src/ML/`)

추론 코드(`discoverex/`)와 독립적으로 동작하는 학습 전용 패키지.

| 파일/디렉터리 | 설명 |
|-------------|------|
| `weight_fitter.py` | `WeightFitter` 클래스 — Nelder-Mead + hinge loss로 `ScoringWeights` scoring 6개 파라미터 최적화 |
| `fit_weights.py` | CLI 진입점 — labeled JSONL → `weights.json` 변환 |
| `data/` | MVP 운영 중 수집된 `VerificationBundle` JSON 저장 디렉터리 |

**의존성 방향**: `ML/` → `discoverex/domain/services/verification.py` (단방향).

---

## 샘플 (`src/sample/`)

| 파일/디렉터리 | 설명 |
|-------------|------|
| `합본.png` | 테스트용 합성 이미지 (composite) |
| `layer/` | 객체별 RGBA 레이어 PNG — 배경.png, 고양이1.png, 고양이2.png, 나비.png, 별.png, MARS.png, 쥐구멍.png |
| `run_validator.py` | 5-Phase 파이프라인 실행 스크립트. GPU 자동 감지 (`torch.cuda.is_available()`) → GPU 가능 시 HF 어댑터, 불가 시 CPU 어댑터 폴백 |
| `test_samples.py` | CPU 어댑터 정의: `CpuPhysicalAdapter` (실계산), `SmartLogicalAdapter` (더미), `SmartVisualAdapter` (compute_visual_similarity 실계산) |

---

## 설정 파일 (`conf/`)

```
conf/
├── gen_verify.yaml
├── verify_only.yaml
├── replay_eval.yaml
├── generate.yaml
├── verify.yaml
├── animate.yaml
├── validator.yaml           # Validator 파이프라인 Hydra 진입점
├── models/
│   ├── hidden_region/
│   ├── inpaint/
│   ├── perception/
│   ├── fx/
│   ├── physical_extraction/ # mobilesam.yaml, dummy.yaml
│   ├── color_edge/          # cv.yaml, dummy.yaml
│   ├── logical_extraction/  # moondream2.yaml, dummy.yaml
│   └── visual_verification/ # yolo_clip.yaml, dummy.yaml
├── adapters/
│   ├── artifact_store/
│   ├── metadata_store/
│   ├── tracker/
│   ├── scene_io/
│   └── report_writer/
└── runtime/
    ├── model_runtime/
    └── env/
```

---

## 딜리버리 레이어 (`delivery/spot_the_hidden/`)

| 파일 | 설명 |
|------|------|
| `schema.py` | `GameBundle` = `PlayableScene` + `AnswerKey` + `DeliveryMeta` |
| `cli.py` | Scene JSON → GameBundle JSON 변환 CLI |
| `converter.py` | `Scene` → `GameBundle` 변환 로직 |
| `io.py` | GameBundle I/O |
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
| **`test_validator_pipeline_smoke.py`** | **Dummy 어댑터 기반 Validator E2E 스모크 테스트, ColorEdgeMetadata 시그널 검증** |
| **`test_validator_scoring.py`** | **Phase 5 순수 수식 단위 테스트: resolve_answer(9조건), compute_difficulty(9항), integrate_verification_v2** |
| **`test_validator_e2e.py`** | **Phase 5 수치 사전 계산 + E2E 수치 검증 (integrate_verification_v2 6+3항 수식 기준)** |
| **`test_hf_model_realpath_fallback.py`** | **HFInpaintModel / HFHiddenRegionModel 경로 fallback 검증** |
| `delivery/test_schema_validation.py` | 딜리버리 번들 스키마 |
| `delivery/test_converter_mapping.py` | Scene→Bundle 변환 |
| `delivery/test_scene_to_bundle_artifact.py` | 번들 아티팩트 생성 |
| `delivery/test_front_payload_strips_answer_key.py` | 정답키 제거 검증 |

---

## 오케스트레이터 (`orchestrator/`)

| 파일 | 설명 |
|------|------|
| `prefect_flows.py` | Prefect 플로우 래퍼: `generate_flow()`, `verify_flow()`, `animate_flow()` |

---

## 인프라 (`infra/`)

| 파일 | 설명 |
|------|------|
| `docker-compose.yml` | PostgreSQL + MinIO + MLflow |

---

## 문서 (`docs/`)

```
docs/
├── pipeline-adapter-guide.md
├── handheld-ops-card.md
├── execution-contract.md
└── Validator/
    ├── instruction_1.md        # Validator 파이프라인 설계 명세
    ├── DIR.md                  # 현재 파일 - 디렉토리 구조 문서
    ├── plan_pipeline.md        # Validator 파이프라인 구현 계획 (원본)
    ├── plan_pipeline_R.md      # 구현 계획 수정본
    ├── plan_weights.md         # ScoringWeights 학습 파이프라인 계획 (원본)
    ├── plan_weights_R.md       # 가중치 계획 수정본
    ├── 구현현황.md              # 현재 구현 상태 + 계획 대비 차이 분석
    ├── 수정계획.md              # 설계 피드백 기반 수정 계획
    └── 수정계획2.md             # 2차 수정 계획 (5-Phase, resolve_answer 9조건 등)
```

---

## 컨텍스트 문서 (`.context/`)

| 파일 | 설명 |
|------|------|
| `overview.md` | 프로젝트 아키텍처 및 핸드오프 가이드 |
| `HANDOFF.md` | 핸드오프 문서 |
| `canon.md` | 표준 Scene 계약 참조 |
| `git-conventions.md` | Git 워크플로우 |

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
| **Validator** | **`mobile-sam>=1.0.0`, `ultralytics>=8.0.0`, `bitsandbytes>=0.41.0`, `networkx>=3.0`, `pillow>=11.3.0`, `numpy>=1.26.0`, `opencv-python-headless`** |
| Dev | `mypy`, `pytest`, `ruff`, `pyyaml` |

---

## Validator 5-Phase 파이프라인

| Phase | 모델 / 어댑터 | VRAM 전략 | 출력 |
|-------|-------------|-----------|------|
| Phase 1 | MobileSAM (`hf_mobilesam.py`) | 단독 로드 → 해제 | `PhysicalMetadata` (z_depth_hop, cluster_density, alpha_degree_map) |
| Phase 2 | CvColorEdgeAdapter (`cv_color_edge.py`) | CPU 전용, VRAM 없음 | `ColorEdgeMetadata` (color_contrast, edge_strength, obj_color, hu_moments) |
| Phase 3 | Moondream2 4-bit (`hf_moondream2.py`) | 단독 로드 → 해제 | `LogicalStructure` (degree_map, hop_map, diameter) |
| Phase 4 | YOLOv10-N + CLIP (`hf_yolo_clip.py`) | 병렬 로드 (4GB 미만) | `VisualVerification` (sigma_threshold, drr_slope, similar_count, similar_distance) |
| Phase 5 | 없음 (순수 연산) | VRAM 불필요 | `VerificationBundle` (perception + logical + final) |

---

## 데이터 플로우 아키텍처

```
합본 이미지 + 오브젝트 레이어 (layer/)
        │
        ▼
[Phase 1] MobileSAM - 물리 메타데이터 추출
        │ PhysicalMetadata (z_index, z_depth_hop, cluster_density, alpha_degree_map)
        ├──────────────────────────────────────┐
        ▼                                      │
[Phase 2] CvColorEdgeAdapter - Color&Edge 추출 (CPU)
        │ ColorEdgeMetadata (color_contrast, edge_strength, obj_color_map, hu_moments_map)
        │                                      │
        └──────────────┬───────────────────────┘
                       ▼
[Phase 3] Moondream2 - 논리 관계 추출 (Scene Graph)
        │ LogicalStructure (degree_map, hop_map, diameter)
        │
        ▼
[Phase 4] YOLOv10-N + CLIP - 시각적 검증 + visual similarity
        │ VisualVerification (sigma_threshold, drr_slope, similar_count, similar_distance)
        │
        ▼
[Phase 5] 순수 연산 - resolve_answer(9조건) + 스코어링
        │ VerificationBundle (perception + logical + final)
        ▼
Delivery CLI → 백엔드 전송
```
