# Discoverex Generate Spec (Current Concrete Behavior)

이 문서는 `.context/canon.md`의 Scene 계약을 기준으로,
현재 코드에서 `generate`가 실제로 무엇을 하는지 구체적으로 정의합니다.

목적:

* `generate`의 입력, 단계, 산출물, 실패 경계를 한 문서에서 본다
* 이상적 제품 설명이 아니라 현재 구현 기준의 실제 동작을 기록한다
* placeholder와 제품 갭은 구분하되, 어느 단계에서 발생하는지 명확히 한다

## 1) 한 줄 정의

현재 `generate`는
`background_asset_ref`를 받아 후보 region 생성, inpaint, composite, verification, persistence를 순서대로 수행하고
최종적으로 canonical `scene.json` 경로를 반환하는 scene assembly pipeline이다.

중요:

* 배경 이미지를 새로 생성하지 않는다
* 현재 goal/answer 일부는 pipeline placeholder 규칙으로 채워진다
* orchestration 성공과 quality pass는 별개다

## 2) 진입점

코드 기준 진입점:

* use case: `src/discoverex/application/use_cases/gen_verify/orchestrator.py`
* Prefect flow: `src/discoverex/flows/generate.py`
* flow payload builder: `src/discoverex/flows/common.py`

v2 명령 기준 입력:

* command: `generate`
* required arg: `background_asset_ref`

정상 종료 시 반환 payload:

* `scene_id`
* `version_id`
* `status`
* `scene_json`

실패 시 flow 레벨 canonical error payload:

* `status=failed`
* `failure_reason`
* `metadata.command=generate`
* `metadata.error_type`
* `scene_id=""`
* `version_id=""`
* `scene_json=""`

## 3) 입력 계약

현재 `generate`의 실질 입력은 아래 두 층이다.

### 3.1 사용자/호출자 입력

필수:

* `background_asset_ref: str`

의미:

* local path
* S3/MinIO URI
* 기타 URL 성격의 ref
* synthetic ref (`bg://dummy`)도 허용

현재 구현상 중요한 제약:

* 파일 경로가 아니어도 pipeline은 진행될 수 있다
* 단, 비파일 ref는 hidden region detection에서 fallback layout으로 내려갈 수 있다

### 3.2 실행 컨텍스트 입력

Hydra/bootstrapped context에서 주입:

* runtime width/height/config_version
* model versions (`hidden_region`, `inpaint`, `perception`, `fx`)
* adapters (`artifact_store`, `metadata_store`, `tracker`, `scene_io`, `report_writer`)
* thresholds (`logical_pass`, `perception_pass`, `final_pass`)

즉 `generate` 품질은 단순히 `background_asset_ref` 하나가 아니라
runtime profile + adapter wiring + model adapter 선택의 영향을 받는다.

## 4) 단계별 동작

현재 구현 흐름은 아래와 같다.

### 4.1 Run ID 발급

`generate_run_ids()`가 아래 ID를 만든다.

* `scene_id`
* `version_id`
* `pipeline_run_id`

의미:

* `scene_id`: scene 계열 식별자
* `version_id`: 이번 생성 산출 version
* `pipeline_run_id`: 실행 단위 식별자

### 4.2 Model handle 로드

context에서 아래 모델 핸들을 로드한다.

* hidden region
* inpaint
* perception
* fx

중요:

* 이 단계는 model adapter 선택과 runtime profile에 따라 실제 HF 경로 또는 dummy/placeholder 경로를 탈 수 있다
* `generate`는 네 모델을 모두 사용 가능한 것으로 가정하고 orchestration을 시작한다

### 4.3 Background 조립

`build_background()`는 `background_asset_ref`와 runtime width/height로 `Background`를 만든다.

현재 동작:

* `Background.asset_ref = input ref`
* `Background.width/height = runtime config 값`
* 배경 픽셀 분석으로 width/height를 읽지 않는다

파일 입력인 경우 보조 동작:

* scene 작업 디렉토리 하위 `layers/base/`로 복사
* `background.metadata["source_background_ref"]`에 원본 ref 저장
* `background.asset_ref`는 복사된 로컬 경로로 치환

즉 현재 background는 "생성 결과"가 아니라 "입력 참조를 materialize한 베이스 레이어"다.

### 4.4 Hidden Region 생성

`generate_regions()` 첫 단계에서 `hidden_region_model.predict()`를 호출한다.

입력:

* `image_ref=background.asset_ref`
* `width`, `height`

출력:

* bbox tuple 목록

이 bbox들은 `build_candidate_regions()`를 통해 `Region[]`로 바뀐다.

현재 고정 규칙:

* 첫 번째 region은 `role=answer`
* 나머지 region은 `role=candidate`
* `source=candidate_model`
* `attributes.proposal_rank`가 순위로 기록된다

중요한 현재 의미:

* 정답은 추론/검색 결과로 확정되는 것이 아니라 "첫 번째 후보가 정답"이라는 pipeline 규칙으로 정해진다
* hidden region 모델이 fallback bbox를 주면 answer 역시 그 fallback ordering에 종속된다

### 4.5 Region별 Inpaint 수행

각 region에 대해 `inpaint_model.predict()`를 호출한다.

입력 핵심:

* `image_ref=background.asset_ref`
* `region_id`
* `bbox`
* `output_path=<scene_dir>/layers/inpaint/...png`
* `composite_base_ref=background.asset_ref`
* `generation_prompt="repair hidden object region naturally"`

현재 concrete behavior:

* prompt planner가 없다
* goal type에 따라 프롬프트가 달라지지 않는다
* object class / relation semantics / count intent를 프롬프트에 반영하지 않는다

inpaint 결과에서 사용할 수 있는 값:

* `patch_image_ref`
* `composited_image_ref`
* 기타 quality/model metadata

region 업데이트 규칙:

* `region.source`는 `inpaint`로 바뀐다
* prediction detail이 `region.attributes`에 합쳐진다

background metadata 보조 기록:

* 마지막으로 관측된 `composited_image_ref`는 `background.metadata["inpaint_composited_ref"]`
* 각 patch layer 후보는 `background.metadata["inpaint_layer_candidates"]`에 기록

주의:

* 현재 루프는 region마다 같은 base background를 기준으로 호출한다
* 여러 region이 있을 때 multi-step 누적 합성의 엄밀한 보장은 문서화되어 있지 않다
* 최종 `inpaint_composited_ref`는 마지막 region의 결과가 대표값이 될 수 있다

### 4.6 Scene 골격 조립

`build_scene()`가 canonical `Scene` 객체를 구성한다.

현재 채움 규칙:

* `meta.status = candidate`
* `meta.model_versions = context model versions`
* `background = 앞 단계 결과`
* `regions = inpaint 이후 region 목록`
* `composite.final_image_ref = ""` 초기값
* `layers.items`에는 base layer 1개를 먼저 생성

현재 goal placeholder:

* `goal.goal_type = relation`
* `goal.constraint_struct.description = "select target region based on relation template"`
* `goal.scope_region_ids = 모든 region id`
* `goal.answer_form = region_select`

현재 answer placeholder:

* region이 있으면 첫 번째 region id를 정답으로 설정
* `uniqueness_intent = true`

즉 현재 `generate`는 goal planning을 수행하지 않고,
"region 후보군이 있고 첫 번째가 정답인 relation puzzle" 형태로 scene을 조립한다.

### 4.7 Composite / FX

`compose_scene()`가 `fx_model.predict()`를 호출한다.

입력:

* `image_ref`: 기본은 background ref
* 단, `background.metadata["inpaint_composited_ref"]`가 있으면 그것을 우선 사용
* `params.output_path = <scene_dir>/composite.png`
* `params.prompt = "hidden object puzzle scene"`

현재 의미:

* scene-aware final render planner는 없다
* fx prompt도 사실상 고정 문자열이다
* output path에 파일이 생기면 그 경로를 최종 image ref로 채택한다
* 파일이 없으면 adapter가 돌려준 ref 또는 background ref로 fallback한다

`.context/generation-gaps-and-placeholders.md` 기준으로,
현재 `fx=hf`도 placeholder 이미지 산출일 수 있다.

### 4.8 Layer stack 확정

`_finalize_layers()`가 아래 레이어를 추가한다.

* inpaint patch layer들
* pre-fx composite layer (inpaint composite가 background와 다를 때)
* final fx layer

현재 레이어 모델은 canonical spec 바깥의 runtime 확장이다.

의미:

* `scene.json`은 canonical field 외에 현재 엔진의 `layers` 구조도 함께 가진다
* layer 정보는 render provenance와 디버깅에는 유용하지만, 정답 판정 기준은 아니다

### 4.9 Verification

`verify_scene()`는 generate 내부에서 즉시 호출된다.

논리 검증:

* `run_logical_verification(scene, pass_threshold=...)`

지각 검증:

* perception 모델에 composite 이미지 ref와 region 목록을 넘겨 confidence를 받는다

최종 통합:

* `integrate_verification(logical, perception, pass_threshold=...)`
* `scene.verification` 갱신
* `scene.difficulty.estimated_score = 1.0 - final.total_score`
* `scene.meta.status = approved | failed`

중요:

* `generate` 성공 후에도 scene status는 `failed`일 수 있다
* 이는 pipeline crash가 아니라 quality gate 탈락이다

### 4.10 Persistence / Tracking

마지막 단계:

* artifact store에 scene bundle 저장
* metadata store upsert
* verification report 작성
* tracker에 run 기록

현재 기대 산출물:

* `scene.json`
* `verification.json`
* `composite.png`

payload에는 최종적으로 `scene_json` 경로가 포함된다.

## 5) 현재 generate가 보장하는 것

현재 코드 기준으로 보장 가능한 것은 아래에 가깝다.

* canonical Scene 구조를 가진 JSON 산출
* region / answer / verification / difficulty 필드 채움
* artifact store / metadata store / tracker에 일관된 기록
* orchestration layer에서 재현 가능한 generate 실행 체인

반대로 아직 보장하지 않는 것:

* text-to-image 배경 생성
* semantics-aware goal planning
* answer uniqueness의 의미 기반 보장
* product-grade final composite
* 실제 이미지 내용과 goal/answer의 고품질 정합성

## 6) 현재 구현의 핵심 placeholder

generate를 읽을 때 특히 아래를 placeholder로 이해해야 한다.

* background는 생성이 아니라 ref passthrough/materialization
* answer는 첫 번째 region으로 고정
* goal은 relation template placeholder
* inpaint prompt는 고정 문자열
* fx prompt도 고정 문자열
* final composite는 adapter에 따라 placeholder artifact일 수 있음

즉 현재 `generate`는 "의미 기반 퍼즐 생성기"라기보다
"scene contract를 채우는 실행 가능한 assembly pipeline"에 더 가깝다.

## 7) 설계상 다음 구체화 포인트

generate를 제품 방향으로 구체화하려면 최소 아래가 필요하다.

1. Goal planner 도입
2. answer selection 근거를 region ranking과 분리해 명시화
3. inpaint prompt provenance 저장
4. multi-region compositing semantics 명확화
5. fx 단계의 real render contract 확정
6. `layers`를 canon에 편입할지 runtime extension으로 유지할지 결정

## 8) 우선 참고할 파일

* `src/discoverex/application/use_cases/gen_verify/orchestrator.py`
* `src/discoverex/application/use_cases/gen_verify/region_pipeline.py`
* `src/discoverex/application/use_cases/gen_verify/scene_builder.py`
* `src/discoverex/application/use_cases/gen_verify/composite_pipeline.py`
* `src/discoverex/application/use_cases/gen_verify/verification_pipeline.py`
* `src/discoverex/flows/generate.py`
