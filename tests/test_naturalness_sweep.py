from __future__ import annotations

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
    assert "adapters.tracker.experiment_name=discoverex-naturalness-search" in first["job_spec"]["inputs"]["overrides"]


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
                "job_spec": {"job_name": "job-1", "inputs": {"args": {}, "overrides": []}},
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
