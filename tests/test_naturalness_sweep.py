from __future__ import annotations

import json
from pathlib import Path

from infra.register.naturalness_sweep import build_sweep_manifest, submit_manifest


def test_build_sweep_manifest_expands_scenarios_and_combos(tmp_path: Path) -> None:
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
    - profile=generator_pixart_gpu_v2_hidden_object
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "sweep.yaml"
    sweep_spec.write_text(
        f"""
sweep_id: test-sweep
base_job_spec: {base_job_spec.name}
experiment_name: discoverex-naturalness-search
scenarios:
  - scenario_id: s1
    background_prompt: harbor
    object_prompt: key
  - scenario_id: s2
    background_prompt: attic
    object_prompt: compass
parameters:
  models/inpaint.edge_blend_strength: ["0.12", "0.24"]
  models/inpaint.core_blend_strength: ["0.18", "0.30"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    assert manifest["sweep_id"] == "test-sweep"
    assert manifest["combo_count"] == 4
    assert manifest["scenario_count"] == 2
    assert manifest["job_count"] == 8
    first = manifest["jobs"][0]
    assert first["job_spec"]["inputs"]["args"]["sweep_id"] == "test-sweep"
    assert first["job_spec"]["inputs"]["args"]["scenario_id"] in {"s1", "s2"}
    assert (
        "adapters.tracker.experiment_name=discoverex-naturalness-search"
        in first["job_spec"]["inputs"]["overrides"]
    )
    assert first["job_spec"]["outputs_prefix"].startswith(
        "exp/discoverex-naturalness-search/test-sweep/"
    )


def test_submit_manifest_defaults_to_naturalness_deployment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def _fake_submit_job_spec(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {"flow_run_id": "run-123"}

    monkeypatch.setattr(
        "infra.register.naturalness_sweep._load_submit_job_spec",
        lambda: _fake_submit_job_spec,
    )

    manifest = {
        "sweep_id": "test-sweep",
        "search_stage": "coarse",
        "experiment_name": "discoverex-naturalness-search-test",
        "combo_count": 1,
        "scenario_count": 1,
        "job_count": 1,
        "jobs": [
            {
                "job_name": "job-1",
                "combo_id": "combo-001",
                "scenario_id": "scene-001",
                "job_spec": {
                    "job_name": "job-1",
                    "inputs": {"args": {}, "overrides": []},
                },
            }
        ],
    }

    result = submit_manifest(
        manifest,
        prefect_api_url="https://prefect.example/api",
        branch="dev",
        experiment="naturalness",
        deployment=None,
        dry_run=False,
    )

    assert captured["deployment"] == "discoverex-naturalness-experiment-dev"
    assert result["deployment"] == "discoverex-naturalness-experiment-dev"
    assert result["results"][0]["deployment"] == "discoverex-naturalness-experiment-dev"


def test_build_sweep_manifest_supports_baseline_without_parameters(
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
    - profile=generator_pixart_gpu_v2_hidden_object
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "sweep.yaml"
    sweep_spec.write_text(
        f"""
sweep_id: tenpack
base_job_spec: {base_job_spec.name}
experiment_name: discoverex-naturalness-tenpack
fixed_overrides:
  - runtime.model_runtime.seed=7
scenarios:
  - scenario_id: s1
    background_prompt: harbor
    object_prompt: key | note | glass
  - scenario_id: s2
    background_prompt: attic
    object_prompt: compass | watch | letter
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    assert manifest["combo_count"] == 1
    assert manifest["scenario_count"] == 2
    assert manifest["job_count"] == 2
    assert manifest["jobs"][0]["combo_id"] == "combo-001"
    assert (
        "runtime.model_runtime.seed=7"
        in manifest["jobs"][0]["job_spec"]["inputs"]["overrides"]
    )


def test_build_sweep_manifest_supports_variant_pack_jobs(tmp_path: Path) -> None:
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
    - profile=generator_pixart_gpu_v2_hidden_object
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "sweep.yaml"
    sweep_spec.write_text(
        f"""
sweep_id: tenpack-variants
base_job_spec: {base_job_spec.name}
experiment_name: discoverex-naturalness-tenpack-variants
scenarios:
  - scenario_id: s1
    background_prompt: harbor
    object_prompt: key | note | glass
variants:
  - variant_id: baseline
    overrides:
      - models.inpaint.edge_blend_strength=0.18
  - variant_id: strong
    overrides:
      - models.inpaint.edge_blend_strength=0.24
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    assert manifest["combo_count"] == 1
    assert manifest["variant_count"] == 2
    assert manifest["job_count"] == 1
    job = manifest["jobs"][0]["job_spec"]
    assert "flows/generate=inpaint_variant_pack" in job["inputs"]["overrides"]
    assert job["inputs"]["args"]["variant_count"] == 2
    assert "baseline" in job["inputs"]["args"]["variant_specs_json"]
    assert job["outputs_prefix"].startswith(
        "exp/discoverex-naturalness-tenpack-variants/tenpack-variants/"
    )


def test_build_sweep_manifest_supports_fixed_replay_inputs(tmp_path: Path) -> None:
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
  overrides:
    - profile=generator_pixart_gpu_v2_hidden_object
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "sweep.yaml"
    sweep_spec.write_text(
        f"""
sweep_id: replay
base_job_spec: {base_job_spec.name}
experiment_name: discoverex-naturalness-replay
scenarios:
  - scenario_id: s1
    background_asset_ref: /app/src/sample/fixed_fixtures/backgrounds/bg.png
    object_image_ref: /app/src/sample/fixed_fixtures/objects/object.png
    object_mask_ref: /app/src/sample/fixed_fixtures/objects/object.mask.png
    raw_alpha_mask_ref: /app/src/sample/fixed_fixtures/objects/object.raw-alpha.png
    object_prompt: key
    region_id: replay-1
    bbox:
      x: 10
      y: 20
      w: 30
      h: 40
variants:
  - variant_id: baseline
    overrides:
      - models.inpaint.overlay_alpha=0.45
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    job = manifest["jobs"][0]["job_spec"]
    assert job["inputs"]["args"]["object_image_ref"].endswith("object.png")
    assert job["inputs"]["args"]["object_mask_ref"].endswith("object.mask.png")
    assert job["inputs"]["args"]["raw_alpha_mask_ref"].endswith("object.raw-alpha.png")
    assert job["inputs"]["args"]["bbox"] == {"x": 10, "y": 20, "w": 30, "h": 40}


def test_build_sweep_manifest_case_per_run_expands_policy_jobs(tmp_path: Path) -> None:
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
    - profile=generator_pixart_gpu_v2_hidden_object
""".strip()
        + "\n",
        encoding="utf-8",
    )
    sweep_spec = tmp_path / "sweep.yaml"
    sweep_spec.write_text(
        f"""
sweep_id: generic-search
execution_mode: case_per_run
base_job_spec: {base_job_spec.name}
experiment_name: discoverex-naturalness-generic
scenarios:
  - scenario_id: s1
    background_prompt: harbor
    object_prompt: key
  - scenario_id: s2
    background_prompt: attic
    object_prompt: compass
variants:
  - variant_id: p01
    overrides:
      - models.inpaint.overlay_alpha=0.35
  - variant_id: p02
    overrides:
      - models.inpaint.overlay_alpha=0.45
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    assert manifest["execution_mode"] == "case_per_run"
    assert manifest["policy_count"] == 2
    assert manifest["job_count"] == 4
    first = manifest["jobs"][0]["job_spec"]
    assert first["inputs"]["args"]["policy_id"] in {"p01", "p02"}
    assert "flows/generate=inpaint_variant_pack" not in first["inputs"]["overrides"]
    assert "models.inpaint.overlay_alpha=0.35" in first["inputs"]["overrides"] or (
        "models.inpaint.overlay_alpha=0.45" in first["inputs"]["overrides"]
    )


def test_collect_naturalness_sweep_aggregates_policy_results(tmp_path: Path) -> None:
    from infra.register.collect_naturalness_sweep import main as collect_main

    artifacts_root = tmp_path / "artifacts"
    cases_dir = (
        artifacts_root
        / "experiments"
        / "naturalness_sweeps"
        / "generic-search"
        / "cases"
    )
    cases_dir.mkdir(parents=True)
    payloads = [
        {
            "sweep_id": "generic-search",
            "policy_id": "p01",
            "scenario_id": "s1",
            "status": "completed",
            "naturalness_metrics": {
                "naturalness.overall_score": 0.8,
                "naturalness.avg_placement_fit": 0.7,
                "naturalness.avg_seam_visibility": 0.2,
                "naturalness.avg_saliency_lift": 0.3,
            },
        },
        {
            "sweep_id": "generic-search",
            "policy_id": "p01",
            "scenario_id": "s2",
            "status": "completed",
            "naturalness_metrics": {
                "naturalness.overall_score": 0.6,
                "naturalness.avg_placement_fit": 0.5,
                "naturalness.avg_seam_visibility": 0.4,
                "naturalness.avg_saliency_lift": 0.2,
            },
        },
        {
            "sweep_id": "generic-search",
            "policy_id": "p02",
            "scenario_id": "s1",
            "status": "completed",
            "naturalness_metrics": {
                "naturalness.overall_score": 0.7,
                "naturalness.avg_placement_fit": 0.6,
                "naturalness.avg_seam_visibility": 0.3,
                "naturalness.avg_saliency_lift": 0.25,
            },
        },
    ]
    for index, payload in enumerate(payloads, start=1):
        (cases_dir / f"case-{index:02d}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
    submitted = tmp_path / "submitted.json"
    submitted.write_text(
        json.dumps(
            {
                "sweep_id": "generic-search",
                "results": [
                    {"policy_id": "p01", "scenario_id": "s1"},
                    {"policy_id": "p01", "scenario_id": "s2"},
                    {"policy_id": "p02", "scenario_id": "s1"},
                    {"policy_id": "p02", "scenario_id": "s2"},
                ],
            }
        ),
        encoding="utf-8",
    )
    output_json = tmp_path / "collected.json"
    output_csv = tmp_path / "collected.csv"

    import sys

    argv = sys.argv
    sys.argv = [
        "collect_naturalness_sweep.py",
        "--submitted-manifest",
        str(submitted),
        "--artifacts-root",
        str(artifacts_root),
        "--output-json",
        str(output_json),
        "--output-csv",
        str(output_csv),
    ]
    try:
        assert collect_main() == 0
    finally:
        sys.argv = argv

    collected = json.loads(output_json.read_text(encoding="utf-8"))
    assert collected["missing_case_count"] == 1
    assert collected["policy_count"] == 2
    assert collected["policies"][0]["policy_id"] == "p02"
    assert collected["policies"][1]["policy_id"] == "p01"
    assert collected["policies"][1]["mean_overall_score"] == 0.7
