# Single Object Debug Flow

이 문서는 LayerDiffuse 기반 단일 오브젝트 생성 디버그 플로우의 계약을 정의합니다.

## 목적

`generate_verify_v2`의 오브젝트 생성 단계를 단일 실행으로 분리해서, 어떤 단계에서 이미지가 손상되는지 추적합니다.

핵심 목표:
- LayerDiffuse + RealVisXL5 조합의 단일 오브젝트 생성
- 생성 직후 RGBA와 alpha 분리 결과를 별도 저장
- SAM/마스크 적용 이후 산출물과 placement 처리 이후 산출물을 함께 저장
- 모든 디버그 산출물을 worker manifest에 포함해서 MinIO 업로드 대상으로 노출
- 각 산출물에 stable `export_key`를 부여

## 실행 형태

- `inputs.command`: `generate`
- `inputs.overrides`: `flows/generate=single_object_debug`
- 권장 모델 설정:
  - `models/object_generator=layerdiffuse`
  - `models.object_generator.model_id=SG161222/RealVisXL_V5.0`

## 입력 인자

- `object_prompt`: 생성할 오브젝트 프롬프트
- `object_negative_prompt`: 네거티브 프롬프트
- `object_generation_size`: 생성 캔버스 크기. 기본값 `512`
- `max_vram_gb`: optional VRAM 상한

이 플로우는 항상 오브젝트 1개만 생성합니다.

## 단계

1. LayerDiffuse object generator로 RGBA 오브젝트를 생성합니다.
2. 생성 직후 RGBA에서 아래 4개를 분리/보존합니다.
   - alpha 없는 RGB 미리보기
   - alpha 채널 흑백 이미지
   - 최종 RGBA PNG
   - pre-SAM RGBA 체크포인트
3. SAM/alpha 결합 마스크 추출 결과를 보존합니다.
4. placement 준비 단계의 처리된 오브젝트와 처리된 마스크를 보존합니다.
5. output manifest와 worker artifact manifest에 export key를 기록합니다.

현재 LayerDiffuse 경로에서는 `pre_sam_rgba`와 `final_rgba`가 동일 파일 계열입니다. 이유는 transparent decoder가 object generator 단계에서 이미 RGBA를 직접 생성하기 때문입니다.

## 필수 산출물

모든 산출물은 `artifacts_root/object_debug/<job_id>/outputs/original/<region_id>/` 아래에 canonical copy를 둡니다.

- `rgb_preview`
  - 파일: `candidate.rgb-preview.png`
  - 설명: alpha 제거 RGB 미리보기
- `alpha_mask`
  - 파일: `candidate.alpha-mask.png`
  - 설명: alpha 채널만 저장한 흑백 이미지
- `final_rgba`
  - 파일: `candidate.final-rgba.png`
  - 설명: object generator가 낸 최종 RGBA
- `pre_sam_rgba`
  - 파일: `candidate.pre-sam-rgba.png`
  - 설명: SAM 적용 전 RGBA 체크포인트
- `sam_object`
  - 파일: `sam.object.png`
  - 설명: SAM 또는 alpha 기반 mask resolve 이후 RGBA
- `raw_alpha_mask`
  - 파일: `sam.raw-alpha-mask.png`
  - 설명: generator RGBA에서 보존한 raw alpha
- `processed_object`
  - 파일: `processed.object.png`
  - 설명: placement 준비 이후 처리된 오브젝트
- `processed_mask`
  - 파일: `processed.mask.png`
  - 설명: placement 준비 이후 처리된 마스크

## output manifest

`outputs/output_manifest.json`은 아래 정보를 포함해야 합니다.

- `flow`
- `job_id`
- `region_id`
- `generated_object`
- `exports[]`

각 `exports[]` 항목은 아래 필드를 가집니다.

- `export_key`
- `logical_name`
- `relative_path`
- `description`
- `source_ref`

## MinIO 업로드 경로

worker는 engine artifact manifest의 `relative_path` 기준으로 업로드합니다. 이 플로우는 다음을 보장합니다.

- canonical debug 파일들은 전부 worker manifest에 포함됩니다.
- `output_manifest.json`도 함께 포함됩니다.
- `collect_worker_artifacts(...)`를 사용하므로 output 디렉터리 하위 파일이 누락되지 않습니다.

## 예시 Job Spec

```yaml
run_mode: repo
engine: discoverex
entrypoint:
  - prefect_flow.py:run_generate_job_flow
config: null
job_name: prod-genobjdebug-none-realvisxl5-none-8gb
inputs:
  contract_version: v2
  command: generate
  config_name: generate
  config_dir: conf
  args:
    object_prompt: antique brass key
    object_negative_prompt: blurry, low quality, artifact
    object_generation_size: 512
  overrides:
    - profile=generator_pixart_gpu_v2_hidden_object
    - runtime/model_runtime=gpu
    - flows/generate=single_object_debug
    - runtime.model_runtime.batch_size=1
    - runtime.width=512
    - runtime.height=512
    - runtime.background_upscale_factor=2
    - runtime.model_runtime.enable_attention_slicing=true
    - runtime.model_runtime.enable_vae_slicing=true
    - runtime.model_runtime.enable_vae_tiling=true
    - runtime.model_runtime.enable_xformers_memory_efficient_attention=true
    - runtime.model_runtime.enable_channels_last=true
    - models/object_generator=layerdiffuse
    - models.object_generator.model_id=SG161222/RealVisXL_V5.0
    - models.object_generator.sampler=dpmpp_sde_karras
    - models.object_generator.dtype=float16
    - models.object_generator.precision=fp16
    - models/hidden_region=dummy
    - models/perception=dummy
    - models/inpaint=dummy
    - models/fx=dummy
    - runtime.model_runtime.offload_mode=sequential
  runtime:
    mode: worker
    bootstrap_mode: none
    extras:
      - tracking
      - storage
      - ml-gpu
      - validator
    extra_env: {}
env: {}
outputs_prefix: null
```
