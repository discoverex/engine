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

Current supported SSOT:

- object-quality sweep specs consumed by `./bin/cli prefect sweep run|collect`

Typical top-level fields:

- `sweep_id`: stable identifier for the sweep
- `search_stage`: coarse/fine/freeform label used in results
- `experiment_name`: MLflow experiment name
- `base_job_spec`: relative path to the standard job spec
- `fixed_overrides`: Hydra overrides applied to every run
- `scenario`: shared args passed to every run
- `parameters`: parameter grid expanded into combinations

Example:

```yaml
sweep_id: object-quality.example.v1
search_stage: coarse
experiment_name: object-quality.example.v1
base_job_spec: ../../specs/job/object_generation.standard.yaml
fixed_overrides:
  - adapters/tracker=mlflow_server
  - runtime.model_runtime.seed=7
scenario:
  scenario_id: transparent-three-object-quality
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
```

## Submit And Collect

Project CLI wrappers:

```bash
./bin/cli prefect sweep run
./bin/cli prefect sweep run --deployment discoverex-generate-batch
./bin/cli prefect sweep collect --submitted-manifest /tmp/object-quality.submitted.json
./bin/cli prefect sweep collect --sweep-spec infra/ops/specs/sweep/object_generation/transparent_three_object.quality.v1.yaml
```

Low-level modules:

```bash
uv run python -m infra.ops.object_generation_sweep <spec.yaml>
uv run python -m infra.ops.collect_object_generation_sweep --submitted-manifest <submitted.json>
```

Default submitted manifest location for the supported CLI surface:

- `infra/ops/manifests/<sweep-id>.submitted.json`
