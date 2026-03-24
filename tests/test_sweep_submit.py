from __future__ import annotations

from pathlib import Path

from infra.ops.sweep_submit import build_standard_spec, build_sweep_manifest, submit_manifest


def test_build_sweep_manifest_preserves_object_generation_canonical_shape(
    tmp_path: Path,
) -> None:
    base_job_spec = tmp_path / "base.yaml"
    base_job_spec.write_text(
        """
run_mode: repo
engine: discoverex
job_name: base
inputs:
  contract_version: v2
  command: generate
  config_name: generate
  config_dir: conf
  args:
    object_prompt: old
  overrides:
    - flows/generate=object_only
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "sweep.yaml"
    sweep_spec.write_text(
        f"""
sweep_id: object-quality.test
base_job_spec: {base_job_spec.name}
experiment_name: object-quality.test
scenario:
  scenario_id: transparent-three-object-quality
  object_prompt: butterfly | antique brass key | dinosaur
parameters:
  models.object_generator.default_num_inference_steps: ["5", "8"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    assert manifest["standard_spec"]["execution"]["runner_type"] == "object_generation"
    assert manifest["standard_spec"]["scenarios"][0]["scenario_id"] == "transparent-three-object-quality"
    assert manifest["sweep_type"] == "object_generation"
    assert manifest["collector_adapter"] == "object_generation"
    assert manifest["case_dir_name"] == "object_generation_sweeps"
    assert manifest["scenario_count"] == 1
    assert manifest["policy_count"] == 2


def test_build_sweep_manifest_normalizes_combined_spec(
    tmp_path: Path,
) -> None:
    base_job_spec = tmp_path / "base.yaml"
    base_job_spec.write_text(
        """
run_mode: repo
engine: discoverex
job_name: base
inputs:
  contract_version: v2
  command: generate
  config_name: generate
  config_dir: conf
  args:
    background_prompt: old
    object_prompt: old
  overrides: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "combined.yaml"
    sweep_spec.write_text(
        f"""
sweep_id: combined.test
base_job_spec: {base_job_spec.name}
experiment_name: combined.test
execution_mode: case_per_run
scenarios:
  - scenario_id: scene-001
    replay_fixture_ref: /tmp/replay.json
variants:
  - variant_id: baseline
    overrides:
      - models.inpaint.edge_blend_strength=0.18
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    assert manifest["standard_spec"]["execution"]["runner_type"] == "combined"
    assert manifest["standard_spec"]["execution"]["mode"] == "case_per_run"
    assert manifest["sweep_type"] == "combined"
    assert manifest["collector_adapter"] == "combined"
    assert manifest["case_dir_name"] == "naturalness_sweeps"
    assert manifest["policy_count"] == 1
    assert manifest["jobs"][0]["policy_id"] == "baseline"


def test_build_standard_spec_supports_explicit_standard_schema(
    tmp_path: Path,
) -> None:
    base_job_spec = tmp_path / "base.yaml"
    base_job_spec.write_text(
        """
run_mode: repo
engine: discoverex
job_name: base
inputs:
  contract_version: v2
  command: generate
  config_name: generate
  config_dir: conf
  args: {}
  overrides: []
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "standard.yaml"
    sweep_spec.write_text(
        f"""
schema_version: v1
sweep_id: standard.test
search_stage: fine
experiment_name: standard.test
base_job_spec: {base_job_spec.name}
fixed_overrides:
  - adapters/tracker=mlflow_server
scenarios:
  - scenario_id: scene-001
    replay_fixture_ref: /tmp/replay.json
parameters:
  models.inpaint.edge_blend_strength: ["0.18", "0.24"]
variants:
  - variant_id: baseline
    overrides:
      - models.inpaint.core_blend_strength=0.18
execution:
  mode: case_per_run
  runner_type: combined
  collector_adapter: combined
  artifact_namespace: naturalness_sweeps
""".strip()
        + "\n",
        encoding="utf-8",
    )

    standard_spec = build_standard_spec(sweep_spec)

    assert standard_spec["schema_version"] == "v1"
    assert standard_spec["execution"]["runner_type"] == "combined"
    assert len(standard_spec["scenarios"]) == 1
    assert len(standard_spec["parameters"]) == 1


def test_build_sweep_manifest_adds_variant_pack_override_for_combined_variant_pack(
    tmp_path: Path,
) -> None:
    base_job_spec = tmp_path / "base.yaml"
    base_job_spec.write_text(
        """
run_mode: repo
engine: discoverex
job_name: base
inputs:
  contract_version: v2
  command: generate
  config_name: generate
  config_dir: conf
  args:
    background_prompt: old
    object_prompt: old
  overrides:
    - flows/generate=generate_verify_v2
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "combined.yaml"
    sweep_spec.write_text(
        f"""
schema_version: v1
sweep_id: combined.variant-pack
base_job_spec: {base_job_spec.name}
experiment_name: combined.variant-pack
scenarios:
  - scenario_id: scene-001
    replay_fixture_ref: /tmp/replay.json
variants:
  - variant_id: baseline
    overrides:
      - models.inpaint.edge_blend_strength=0.18
execution:
  mode: variant_pack
  runner_type: combined
  collector_adapter: combined
  artifact_namespace: naturalness_sweeps
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    job = manifest["jobs"][0]
    overrides = job["job_spec"]["inputs"]["overrides"]
    assert "flows/generate=inpaint_variant_pack" in overrides


def test_submit_manifest_supports_queue_override_for_combined(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fake_submit_job_spec(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {"flow_run_id": "run-123"}

    monkeypatch.setattr(
        "infra.ops.sweep_submit._load_submit_job_spec",
        lambda: fake_submit_job_spec,
    )

    result = submit_manifest(
        {
            "manifest_version": "v1",
            "spec_version": "v1",
            "sweep_id": "combined.test",
            "search_stage": "replay-fixture",
            "experiment_name": "combined.test",
            "execution": {
                "mode": "case_per_run",
                "runner_type": "combined",
                "collector_adapter": "combined",
                "artifact_namespace": "naturalness_sweeps",
            },
            "sweep_type": "combined",
            "canonical_version": "v1",
            "case_dir_name": "naturalness_sweeps",
            "case_artifact_logical_name": "quality_case_json",
            "collector_adapter": "combined",
            "combo_count": 1,
            "scenario_count": 1,
            "variant_count": 1,
            "policy_count": 1,
            "job_count": 1,
            "jobs": [
                {
                    "job_name": "job-1",
                    "combo_id": "combo-001",
                    "policy_id": "baseline",
                    "scenario_id": "scene-001",
                    "job_spec": {"job_name": "job-1", "inputs": {"args": {}, "overrides": []}},
                }
            ],
        },
        prefect_api_url="https://prefect.example/api",
        purpose="batch",
        experiment="object-quality",
        deployment=None,
        work_queue_name="gpu-fixed-batch",
        dry_run=False,
    )

    assert captured["work_queue_name"] == "gpu-fixed-batch"
    assert result["collector_adapter"] == "combined"
