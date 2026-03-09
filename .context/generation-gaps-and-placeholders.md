# Discoverex Generation Gaps And Placeholders

이 문서는 현재 엔진이 `production-grade image generation pipeline`으로 오해되지 않도록,
생성 경로의 미구현 구간과 placeholder 동작을 기록합니다.

핵심 결론:

* 현재 엔진은 orchestration / artifact / tracking 경로는 실제로 동작한다
* 그러나 배경 생성, 의미 기반 프롬프트 계획, 최종 FX 렌더는 아직 제품 수준이 아니다

## 1) 배경 생성은 현재 없다

현재 파이프라인에서 배경은 생성하지 않습니다.

`background_asset_ref`를 입력으로 받아 그대로 `Background.asset_ref`에 넣습니다.

즉 현재는:

* text prompt로 배경을 생성하지 않음
* diffusion으로 scene background를 합성하지 않음
* 입력 asset ref가 곧 배경의 SSOT

따라서 `bg://dummy`는 생성된 이미지가 아니라 synthetic / non-file background ref입니다.

## 2) hidden region은 실제 detector + fallback 혼합 상태다

`hidden_region=hf` 어댑터는 실제 파일 입력이면 transformers object-detection 경로를 시도합니다.
하지만 입력이 파일이 아니거나 runtime이 맞지 않으면 deterministic bbox fallback으로 내려갑니다.

특히:

* `bg://dummy` 같은 비파일 입력은 detector 대상이 아님
* 이런 경우 현재는 고정된 3개 bbox layout을 반환할 수 있음

즉 최근 검증 run들의 region layout은 "실제 배경 이미지 분석 결과"가 아니라
fallback layout일 가능성이 높습니다.

## 3) 오브젝트 생성 프롬프트는 현재 하드코딩 수준이다

현재 인페인트 단계에서 실질적으로 쓰는 generation prompt는 아래 한 줄입니다.

* `repair hidden object region naturally`

이 의미:

* scene-specific semantic planning 없음
* relation/count/semantic goal에서 prompt를 다르게 구성하지 않음
* object class, style, composition intent를 명시적으로 생성하지 않음
* prompt planner / prompt templating / prompt provenance 저장도 없음

따라서 현재 엔진은 "프롬프트 기반으로 어떤 오브젝트를 만들지 계획하고 생성"하는 구조가 아닙니다.
오히려 "후보 영역을 잡고 그 영역을 자연스럽게 메우는 인페인트"에 더 가깝습니다.

## 4) inpaint는 일부 실제 모델 경로가 있다

현재 `hf_inpaint`는 diffusers img2img 경로를 호출할 수 있습니다.

실제 특징:

* quality score 분류기: `google/vit-base-patch16-224`
* generation model default: `hf-internal-testing/tiny-stable-diffusion-pipe`
* config override에 따라 `stabilityai/stable-diffusion-2-inpainting` 계열 설정 사용
* patch 생성 후 composited image를 만들 수 있음

하지만 이것만으로 full-scene product renderer가 되지는 않습니다.

## 5) 최종 FX / composite는 현재 placeholder다

현재 `fx=hf`라고 해도 final render는 실질적 diffusion 합성이 아닙니다.

현 상태:

* `hf_fx`는 output path를 받으면 실제 이미지 생성 대신 `ensure_output_image()`를 호출
* `ensure_output_image()`는 minimal PNG를 써 넣음
* 따라서 `composite.png`가 존재해도 아주 작은 placeholder 이미지일 수 있음

최근 run에서 확인된 `composite.png`가 매우 작은 파일 크기였던 이유가 이것입니다.

즉 현재의 `final_image_ref`는 "scene contract를 만족하는 artifact 경로"이지,
곧바로 "실제 고품질 최종 합성 이미지"를 의미하지 않습니다.

## 6) verification failure는 현재 자연스러운 결과다

최근 run들이 `scene status=failed`였던 직접 원인은 아래입니다.

* `logical_score`는 높음
* `perception_score`가 매우 낮음
* `final.total_score`가 threshold 미만

이 결과는 현재 생성 경로의 한계와 일관됩니다.

* 배경은 synthetic ref
* hidden region은 fallback bbox 가능
* prompt planning 부재
* final composite는 placeholder

즉 현 단계에서 scene verification pass를 제품 수준으로 기대하면 안 됩니다.

## 7) 아직 없는 것들

현재 부재 또는 미완인 항목:

* text prompt 기반 background generation
* scene-aware prompt planner
* object semantics / relation-aware generation prompt
* real final compositing / rendering
* non-dummy asset ingestion을 전제로 한 end-to-end production image path
* generated visual quality를 기준으로 한 production acceptance tuning

## 8) 현재 엔진을 어떻게 이해해야 하나

현재 엔진은 아래로 이해하는 것이 정확합니다.

* 이미 돌아가는 orchestration contract
* scene/verification artifact contract
* worker-mode MinIO/MLflow integration
* 일부 실제 HF model path
* 그러나 아직 제품 완성형 생성기는 아닌 상태

즉 "실행 가능한 pipeline skeleton + partial model-backed generation path"로 보는 것이 맞습니다.

## 9) 참고 파일

생성 경로를 이해할 때 우선 볼 파일:

* `src/discoverex/application/use_cases/gen_verify/scene_builder.py`
* `src/discoverex/application/use_cases/gen_verify/region_pipeline.py`
* `src/discoverex/adapters/outbound/models/hf_hidden_region.py`
* `src/discoverex/adapters/outbound/models/hf_inpaint.py`
* `src/discoverex/adapters/outbound/models/hf_inpaint_inference.py`
* `src/discoverex/adapters/outbound/models/hf_fx.py`
* `src/discoverex/adapters/outbound/models/fx_artifact.py`
