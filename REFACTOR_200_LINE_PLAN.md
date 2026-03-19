# 200-Line Refactor Execution Plan

## Goal

`tests/test_architecture_constraints.py::test_src_python_files_are_200_lines_or_less`
를 통과시키기 위해, 남은 200라인 초과 `src/discoverex` 파일들을 의미 단위와 책임 단위로 계층적으로 분해한다.

핵심 제약:

- `src` 내부 패키지는 헥사고널 아키텍처를 유지한다.
- 기계적으로 파일을 자르지 않는다.
- facade import 경로는 가능한 유지한다.
- `application`은 orchestration과 정책만 가진다.
- `adapters`는 외부 라이브러리와 런타임 구현만 가진다.
- `flows`는 thin shell이어야 하며 bulk orchestration은 `application/use_cases`로 이동한다.

## Current Offenders

- `src/discoverex/flows/generate_variant_pack.py`
- `src/discoverex/adapters/outbound/models/hidden_object_backends.py`
- `src/discoverex/adapters/outbound/models/pixart_sigma_background_generation.py`
- `src/discoverex/adapters/outbound/models/layerdiffuse_object_generation.py`
- `src/discoverex/adapters/outbound/models/layerdiffuse_transparent_vae.py`

## Execution Order

1. `flows/generate_variant_pack.py`
2. `adapters/outbound/models/hidden_object_backends.py`
3. `adapters/outbound/models/pixart_sigma_background_generation.py`
4. `adapters/outbound/models/layerdiffuse_object_generation.py`
5. `adapters/outbound/models/layerdiffuse_transparent_vae.py`

이 순서를 기본으로 한다. 이유는:

- 먼저 `flows`를 얇게 만들어 `application/use_cases` 경계를 고정해야 한다.
- 그 다음 adapter 대형 파일들을 backend/service/load/runtime 기준으로 나누면 된다.

## 1. Variant Pack Flow

대상:

- `src/discoverex/flows/generate_variant_pack.py`

목표 구조:

- `src/discoverex/flows/generate_variant_pack.py`
  - Prefect flow shell만 유지
  - 입력 수집
  - application use case 호출
  - 완료 로깅
- `src/discoverex/application/use_cases/variantpack/parse.py`
  - variant spec 파싱
  - variant id 정규화
- `src/discoverex/application/use_cases/variantpack/runtime.py`
  - run id 생성
  - prepare dir 계산
  - variant args 파생
  - background reset
- `src/discoverex/application/use_cases/variantpack/config.py`
  - base snapshot + override로 variant config 구성
  - execution snapshot 생성/업데이트
- `src/discoverex/application/use_cases/variantpack/artifacts.py`
  - variant manifest path 계산
  - variant artifact entry 계산
  - variant pack manifest payload 작성용 데이터 조립
- `src/discoverex/application/use_cases/variantpack/execute.py`
  - prepare background/regions/object generation 수행
  - 각 variant 실행 orchestration
  - final payload 조립

세부 원칙:

- `flows/generate_variant_pack.py`는 `_build_context`, `_build_background_stage`, `_inpaint_regions_stage` 같은 task 호출 orchestration만 남긴다.
- variant-specific business orchestration은 `application/use_cases/variantpack/execute.py`로 이동한다.
- manifest 파일 쓰기가 필요하면 `adapters/outbound/io` 헬퍼를 재사용한다.

완료 기준:

- `generate_variant_pack.py` 200라인 이하
- 새 `application/use_cases/variantpack/*` 파일도 각각 200라인 이하

## 2. Hidden Object Backends

대상:

- `src/discoverex/adapters/outbound/models/hidden_object_backends.py`

목표 구조:

- `src/discoverex/adapters/outbound/models/hidden/`
  - `runtime.py`
    - `BackendRuntime`
    - 공통 dtype/runtime helper
  - `rmbg.py`
    - `Rmbg20MaskRefiner`
  - `sam2.py`
    - `Sam2MaskRefiner`
  - `relight.py`
    - `IcLightRelighter`
  - `blend.py`
    - `DiffusionObjectBlendBackend`
    - local runtime handle
  - `__init__.py`
    - 기존 공개 심볼 re-export
- `src/discoverex/adapters/outbound/models/hidden_object_backends.py`
  - facade only

세부 원칙:

- 각 backend class는 자기 로딩/추론/후처리 책임만 가진다.
- 여러 backend가 공유하는 runtime 구성과 공통 helper만 `runtime.py`로 이동한다.
- PIL/diffusers/transformers 직접 호출은 adapter 내부에만 남긴다.

완료 기준:

- facade 제외 모든 파일 200라인 이하
- 기존 import 경로 유지

## 3. PixArt Background Generation

대상:

- `src/discoverex/adapters/outbound/models/pixart_sigma_background_generation.py`

목표 구조:

- `src/discoverex/adapters/outbound/models/background/pixart/`
  - `params.py`
    - request param 파싱
    - default 값 계산
  - `load.py`
    - tokenizer/pipeline load
    - runtime validation
  - `base.py`
    - base image generation
  - `detail.py`
    - image-to-image detail refinement
  - `service.py`
    - `PixArtSigmaBackgroundGenerationModel`
    - public adapter shell
  - `__init__.py`
    - 공개 클래스 re-export
- 기존 파일은 facade only

세부 원칙:

- public model class는 조립과 high-level flow만 가진다.
- tokenizer 재설치/재로드 같은 runtime workaround는 `load.py`에 격리한다.
- base generation과 detail refinement는 같은 파일에 두지 않는다.

완료 기준:

- public shell 파일 200라인 이하
- detail/base/load 분리 후 각 파일 200라인 이하

## 4. LayerDiffuse Object Generation

대상:

- `src/discoverex/adapters/outbound/models/layerdiffuse_object_generation.py`

목표 구조:

- `src/discoverex/adapters/outbound/models/objects/layerdiffuse/`
  - `cache.py`
    - shared cache dir resolution
    - materialized weight/cache helper
  - `load.py`
    - model bootstrap
    - pipeline setup
  - `generate.py`
    - object generation path
  - `service.py`
    - `LayerDiffuseObjectGenerationModel`
  - `__init__.py`
    - public class re-export
- 기존 파일은 facade only

세부 원칙:

- 캐시/모델 로딩/실행은 각각 분리한다.
- service class는 orchestration shell 역할만 한다.

완료 기준:

- facade 포함 모든 파일 200라인 이하

## 5. LayerDiffuse Transparent VAE

대상:

- `src/discoverex/adapters/outbound/models/layerdiffuse_transparent_vae.py`

목표 구조:

- `src/discoverex/adapters/outbound/models/objects/layerdiffuse/vae/`
  - `helpers.py`
    - `zero_module`
    - `checkerboard`
    - 기타 tensor/math helper
  - `unet.py`
    - `UNet1024`
  - `decoder.py`
    - `TransparentVAEDecoder`
  - `__init__.py`
    - 공개 심볼 re-export
- 기존 파일은 facade only

세부 원칙:

- 큰 model 정의와 decoder 정의를 분리한다.
- diffusers/torch class 정의는 adapter 내부에만 남긴다.
- type-ignore 정책이 필요하면 새 파일 단위로 국소화한다.

완료 기준:

- facade 포함 모든 파일 200라인 이하

## Validation

매 단계마다 아래 순서로 확인한다.

1. 대상 파일 라인 수 확인
2. `uv run --extra dev mypy <affected paths>`
3. `uv run --extra dev pytest tests/test_architecture_constraints.py -k 200_lines`
4. 마지막에 `just check`

추가 확인 항목:

- `application`이 adapter 구현 세부사항을 새로 import하지 않았는지
- `flows`가 다시 비대해지지 않았는지
- facade re-export 때문에 순환 import가 생기지 않았는지

## Done Criteria

- 남은 5개 offender가 모두 200라인 이하
- 새로 만든 파일도 예외 없이 200라인 이하
- `tests/test_architecture_constraints.py` 통과
- `just check` 통과
