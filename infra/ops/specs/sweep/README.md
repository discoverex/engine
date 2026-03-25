# Sweep Layout

`infra/ops/specs/sweep` is organized by experiment scope.

- `background_generation/`: experiments that only tune background generation
- `object_generation/`: experiments that only tune object generation
- `patch_selection/`: experiments that only tune patch selection
- `inpaint/`: experiments that only tune inpaint
- `combined/`: experiments spanning two or more stages

Current files use:

- `object_generation/` for single-stage object generation sweeps
- `combined/` for background+object generation and patch-selection+inpaint sweeps

## Sweep Spec Shape

Sweep specs are YAML files that expand into one Prefect run per parameter combination.

Current CLI support uses a standard sweep contract and legacy adapters.

Standard top-level fields:

- `schema_version`: currently `v1`
- `sweep_id`: stable identifier for the sweep
- `search_stage`: coarse/fine/freeform label used in results
- `experiment_name`: MLflow experiment name
- `base_job_spec`: relative path to the standard job spec
- `fixed_overrides`: Hydra overrides applied to every run
- `scenarios`: scenario list expanded across policies
- `parameters`: parameter grid expanded into combinations
- `variants`: optional policy variants
- `execution`: runner/collector metadata

Legacy compatibility:

- `scenario` is still accepted and normalized to `scenarios`
- existing `object_generation/` and `combined/` specs are auto-translated

Example:

```yaml
schema_version: v1
sweep_id: object-quality.example.v1
search_stage: coarse
experiment_name: object-quality.example.v1
base_job_spec: ../../specs/job_specs/object_generation.standard.yaml
fixed_overrides:
  - adapters/tracker=mlflow_server
  - runtime.model_runtime.seed=7
scenarios:
  - scenario_id: transparent-three-object-quality
    object_base_prompt: isolated single object on a transparent background
    object_prompt: butterfly | antique brass key | dinosaur
    object_base_negative_prompt: opaque background, solid background, busy scene
    object_negative_prompt: blurry, low quality, artifact
    object_count: 3
parameters:
  inputs.args.object_prompt_style: ["neutral_backdrop", "transparent_only"]
  inputs.args.object_negative_profile: ["default", "anti_white"]
  models.object_generator.default_num_inference_steps: ["5", "8"]
  models.object_generator.default_guidance_scale: ["1.0", "2.0"]
  inputs.args.object_generation_size: ["512", "640"]
variants: []
execution:
  mode: case_per_run
  runner_type: object_generation
  collector_adapter: object_generation
  artifact_namespace: object_generation_sweeps
```

## Submit And Collect

Project CLI wrappers:

```bash
./bin/cli prefect sweep run
./bin/cli prefect sweep run --deployment discoverex-generate-batch
./bin/cli prefect sweep collect --submitted-manifest /tmp/object-quality.submitted.json
./bin/cli prefect sweep collect --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

Sweep CLI defaults:

- deployment: `discoverex-generate-batch`
- queue: `gpu-fixed-batch`
- `--purpose` is not part of the sweep surface

Low-level modules:

```bash
uv run python -m infra.ops.sweep_submit <spec.yaml>
uv run python -m infra.ops.collect_sweep --submitted-manifest <submitted.json>
```

Default submitted manifest location for the supported CLI surface:

- `infra/ops/manifests/<sweep-id>.submitted.json`
