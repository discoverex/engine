# Object Quality Sweeps

This guide describes the supported sweep design and day-to-day operating procedure for object-quality sweeps.

Object-quality is the current sweep SSOT. Other sweep families remain legacy and are not the primary supported path in this pass.

## Supported Surface

Sweep input is always a YAML spec file passed as `--sweep-spec <path>`.

Supported commands:

- `./bin/cli prefect sweep run --sweep-spec <path>`
- `./bin/cli prefect sweep collect --sweep-spec <path>`

Default state location:

- `infra/ops/manifests/<sweep-id>.submitted.json`

## What A Sweep Does

An object-quality sweep expands a YAML spec into one Prefect flow run per parameter combination.

Each run:

- uses the standard object-generation job spec
- generates the configured object set
- evaluates the generated assets
- writes structured case results and gallery artifacts

The submitter writes a `submitted manifest` containing:

- `sweep_id`
- `policy_id`
- `scenario_id`
- `flow_run_id`
- `deployment`
- `outputs_prefix`

The collector reads those results back and classifies runs as:

- `completed`
- `pending`
- `failed`
- `cancelled`
- `failed_to_collect`
- `not_submitted`

## Sweep Design

The object-quality path uses one spec to describe:

- stable sweep identity via `sweep_id`
- experiment naming via `experiment_name`
- one shared scenario payload
- one parameter grid that expands into `combo_id` values
- one base job spec that becomes the per-run payload

Manifest row identity is:

- `sweep_id`
- `policy_id`
- `scenario_id`

Repeated `sweep run` calls merge by that identity and only overwrite runtime submission fields:

- `flow_run_id`
- `submitted`
- `status`
- optional `deployment`
- optional `updated_at`

## Spec Layout

Example spec:

```yaml
sweep_id: object-quality.realvisxl5-lightning.example.v1
search_stage: coarse
experiment_name: object-quality.realvisxl5-lightning.example.v1
base_job_spec: ../../job_specs/object_generation.standard.yaml
fixed_overrides:
  - adapters/tracker=mlflow_server
  - runtime.model_runtime.seed=7
scenario:
  scenario_id: transparent-three-object-quality
  object_base_prompt: isolated single object on a transparent background
  object_prompt: butterfly | antique brass key | dinosaur
  object_base_negative_prompt: opaque background, solid background, busy scene, environment, multiple objects, floor, wall, clutter
  object_negative_prompt: blurry, low quality, artifact
  object_count: 3
parameters:
  inputs.args.object_prompt_style: ["neutral_backdrop", "transparent_only", "studio_cutout"]
  inputs.args.object_negative_profile: ["default", "anti_white", "anti_white_glow"]
  models.object_generator.default_num_inference_steps: ["5", "8", "12"]
  models.object_generator.default_guidance_scale: ["1.0", "1.5", "2.0", "2.5"]
  inputs.args.object_generation_size: ["512", "640"]
```

## Submit

Default batch deployment:

```bash
./bin/cli prefect sweep run
```

Equivalent explicit form:

```bash
./bin/cli prefect sweep run \
  --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

Explicit deployment and queue override:

```bash
./bin/cli prefect sweep run \
  --deployment discoverex-generate-batch \
  --work-queue-name gpu-fixed-batch-1 \
  --output /tmp/object-quality.submitted.json
```

Low-level equivalent:

```bash
uv run python -m infra.ops.object_generation_sweep \
  infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml \
  --deployment discoverex-generate-batch \
  --output /tmp/object-quality.submitted.json
```

## Collect

From a submitted manifest:

```bash
./bin/cli prefect sweep collect \
  --submitted-manifest /tmp/object-quality.submitted.json
```

From a sweep spec:

```bash
./bin/cli prefect sweep collect \
  --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

Collector outputs:

- JSON summary
- CSV policy ranking
- HTML gallery index

## Retry Strategy

Use the collector output as the source of truth for retries.

- `pending`: do not resubmit yet
- `failed`: candidate for resubmit
- `cancelled`: candidate for resubmit
- `failed_to_collect`: investigate artifact upload or manifest issues, then resubmit if needed
- `not_submitted`: safe to submit

For targeted retries, rerun the submitter with:

- `--submitted-manifest`
- `--retry-missing-limit N`

Retry selection rules:

- only retry-eligible rows are considered
- original manifest job order is preserved
- `--retry-missing-limit N` takes the first `N` eligible rows

## Deployment And Queue Defaults

Purpose-based deployment names:

- `discoverex-generate-standard`
- `discoverex-generate-batch`
- `discoverex-generate-debug`
- `discoverex-generate-backfill`

Queue defaults:

- `standard` -> `gpu-fixed`
- `batch` -> `gpu-fixed-batch`
- `debug` -> `gpu-fixed-debug`
- `backfill` -> `gpu-fixed-backfill`

Submission may still override the queue for isolated runs.

## Operational Notes

- `sweep run` can submit to any compatible generate deployment via `--deployment`
- `sweep run` can override the queue at submit time with `--work-queue-name`
- `collect` derives the default manifest from the sweep spec when you use the CLI wrapper
- a newly submitted sweep normally shows up as `pending` until a worker picks it up or the collector can recover finished artifacts
