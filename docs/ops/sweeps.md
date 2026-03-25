# Sweep 운영 가이드

이 문서는 현재 운영되는 sweep 표면을 정리한다. spec 필드의 상세 shape는 [infra/ops/specs/sweep/README.md](/home/esillileu/discoverex/engine/infra/ops/specs/sweep/README.md)를 source of truth로 본다.

## 1. 현재 sweep 범위

현재 운영 표면은 `./bin/cli prefect sweep run|collect` 이다.

코드와 spec 상 존재하는 주요 범위:

- object-generation sweep
- combined replay fixture sweep
- naturalness 계열 combined sweep
- patch-selection + inpaint 계열 combined sweep

즉, sweep SSOT는 더 이상 object-quality 하나만이 아니다.

## 2. 지원 명령

```bash
./bin/cli prefect sweep run --sweep-spec <path>
./bin/cli prefect sweep collect --sweep-spec <path>
```

낮은 수준 모듈:

```bash
uv run python -m infra.ops.sweep_submit <spec.yaml>
uv run python -m infra.ops.collect_sweep --submitted-manifest <submitted.json>
```

## 3. spec와 manifest 규칙

sweep 입력은 항상 `--sweep-spec <yaml>` 이다.

기본 submitted manifest 위치:

- `infra/ops/manifests/<sweep-id>.submitted.json`

현재 spec 패밀리는 아래 디렉터리 아래에 있다.

- `infra/ops/specs/sweep/object_generation/`
- `infra/ops/specs/sweep/combined/`

세부 필드는 하위 SSOT 문서에 맡긴다.

- `schema_version`
- `sweep_id`
- `search_stage`
- `experiment_name`
- `base_job_spec`
- `fixed_overrides`
- `scenarios`
- `parameters`
- `variants`
- `execution`

## 4. object-generation sweep

대표 spec:

- `infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml`

특징:

- object generation standard spec 기반
- parameter grid 를 Prefect run들로 확장
- collector 가 상태 분류와 결과 집계를 수행

## 5. combined sweep

대표 spec:

- `infra/ops/specs/sweep/combined/patch_selection_inpaint.grid.medium.yaml`
- `infra/ops/specs/sweep/combined/patch_selection_inpaint.replay_fixture.v1.yaml`
- `infra/ops/specs/sweep/combined/patch_selection_inpaint.variant_pack.fivepack.yaml`

특징:

- 배경/오브젝트/패치 선택/인페인트 등 두 개 이상 stage를 함께 다룬다
- `execution.mode` 는 `case_per_run` 또는 `variant_pack` 이 될 수 있다
- collector adapter 는 `combined` 로 정규화된다
- naturalness 결과 아티팩트 namespace 를 사용할 수 있다

## 6. collector 상태 분류

collector 는 submitted row를 다음 상태로 분류할 수 있다.

- `completed`
- `pending`
- `failed`
- `cancelled`
- `failed_to_collect`
- `not_submitted`

retry 판단은 collector 결과를 source of truth로 삼는다.

## 7. deployment와 queue 기본값

sweep surface 기본값:

- deployment: `discoverex-generate-batch`
- queue: `gpu-fixed-batch`

필요하면 제출 시점에 override 가능하다.

- `--deployment`
- `--work-queue-name`

## 8. 관련 문서

- CLI 표면: [docs/ops/cli.md](/home/esillileu/discoverex/engine/docs/ops/cli.md)
- 런타임 모델: [docs/ops/runtime.md](/home/esillileu/discoverex/engine/docs/ops/runtime.md)
- spec shape: [infra/ops/specs/sweep/README.md](/home/esillileu/discoverex/engine/infra/ops/specs/sweep/README.md)
