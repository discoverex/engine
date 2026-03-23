from __future__ import annotations

import json
from pathlib import Path

from infra.register.object_generation_sweep import build_sweep_manifest, submit_manifest
from infra.register.collect_object_generation_sweep import (
    _aggregate,
    _load_env_file,
    _filename_from_object_uri,
    _recover_remote_cases,
)


def test_build_object_generation_sweep_manifest(tmp_path: Path) -> None:
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
fixed_overrides:
  - runtime.model_runtime.seed=7
scenario:
  scenario_id: transparent-three-object-quality
  object_prompt: butterfly | antique brass key | dinosaur
  object_count: 3
parameters:
  models.object_generator.default_num_inference_steps: ["5", "8"]
  models.object_generator.default_guidance_scale: ["1.0", "2.0"]
  inputs.args.object_generation_size: ["512"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = build_sweep_manifest(sweep_spec)

    assert manifest["combo_count"] == 4
    assert manifest["job_count"] == 4
    first = manifest["jobs"][0]["job_spec"]
    assert first["inputs"]["args"]["sweep_id"] == "object-quality.test"
    assert first["inputs"]["args"]["object_generation_size"] == "512"
    assert "runtime.model_runtime.seed=7" in first["inputs"]["overrides"]


def test_submit_manifest_records_flow_run_ids(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    def fake_submit_job_spec(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {"flow_run_id": "run-123"}

    monkeypatch.setattr(
        "infra.register.object_generation_sweep._load_submit_job_spec",
        lambda: fake_submit_job_spec,
    )

    result = submit_manifest(
        {
            "sweep_id": "object-quality.test",
            "search_stage": "coarse",
            "experiment_name": "object-quality.test",
            "combo_count": 1,
            "job_count": 1,
            "jobs": [
                {
                    "job_name": "job-1",
                    "combo_id": "combo-001",
                    "policy_id": "combo-001",
                    "scenario_id": "scenario-001",
                    "job_spec": {"job_name": "job-1", "inputs": {"args": {}, "overrides": []}},
                }
            ],
        },
        prefect_api_url="https://prefect.example/api",
        purpose="batch",
        experiment="object-quality",
        deployment=None,
        dry_run=False,
    )

    assert captured["deployment"] == "discoverex-generate-batch-object-quality"
    assert result["results"][0]["flow_run_id"] == "run-123"


def test_submit_manifest_retries_only_missing_or_unsubmitted(
    monkeypatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    submitted_calls: list[str] = []

    def fake_submit_job_spec(**kwargs):  # type: ignore[no-untyped-def]
        submitted_calls.append(str(kwargs["job_name"]))
        return {"flow_run_id": f"run-{len(submitted_calls)}"}

    artifacts_root = tmp_path / "artifacts"
    cases_dir = (
        artifacts_root
        / "experiments"
        / "object_generation_sweeps"
        / "object-quality.test"
        / "cases"
    )
    cases_dir.mkdir(parents=True, exist_ok=True)
    (cases_dir / "combo-001.json").write_text(
        json.dumps(
            {
                "policy_id": "combo-001",
                "scenario_id": "scenario-001",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "infra.register.object_generation_sweep._load_submit_job_spec",
        lambda: fake_submit_job_spec,
    )

    manifest = {
        "sweep_id": "object-quality.test",
        "search_stage": "coarse",
        "experiment_name": "object-quality.test",
        "combo_count": 3,
        "job_count": 3,
        "jobs": [
            {
                "job_name": "job-1",
                "combo_id": "combo-001",
                "policy_id": "combo-001",
                "scenario_id": "scenario-001",
                "job_spec": {"job_name": "job-1", "inputs": {"args": {}, "overrides": []}},
            },
            {
                "job_name": "job-2",
                "combo_id": "combo-002",
                "policy_id": "combo-002",
                "scenario_id": "scenario-001",
                "job_spec": {"job_name": "job-2", "inputs": {"args": {}, "overrides": []}},
            },
            {
                "job_name": "job-3",
                "combo_id": "combo-003",
                "policy_id": "combo-003",
                "scenario_id": "scenario-001",
                "job_spec": {"job_name": "job-3", "inputs": {"args": {}, "overrides": []}},
            },
        ],
    }
    submitted_manifest = {
        "sweep_id": "object-quality.test",
        "results": [
            {
                "job_name": "job-1",
                "policy_id": "combo-001",
                "scenario_id": "scenario-001",
                "submitted": True,
                "flow_run_id": "run-ok",
            },
            {
                "job_name": "job-2",
                "policy_id": "combo-002",
                "scenario_id": "scenario-001",
                "submitted": True,
                "flow_run_id": "run-missing",
            },
        ],
    }

    result = submit_manifest(
        manifest,
        prefect_api_url="https://prefect.example/api",
        purpose="batch",
        experiment="object-quality",
        deployment=None,
        dry_run=False,
        submitted_manifest=submitted_manifest,
        artifacts_root=artifacts_root,
        retry_missing_limit=1,
    )

    assert submitted_calls == ["job-2"]
    assert len(result["results"]) == 2
    assert any(item["policy_id"] == "combo-002" and item["flow_run_id"] == "run-1" for item in result["results"])


def test_collect_marks_submitted_but_missing_as_failed() -> None:
    output = _aggregate(
        [],
        submitted_manifest={
            "results": [
                {
                    "job_name": "job-1",
                    "policy_id": "combo-001",
                    "scenario_id": "scenario-001",
                    "submitted": True,
                    "flow_run_id": "run-123",
                    "deployment": "dep",
                },
                {
                    "job_name": "job-2",
                    "policy_id": "combo-002",
                    "scenario_id": "scenario-001",
                    "submitted": False,
                    "flow_run_id": "",
                    "deployment": "dep",
                },
            ]
        },
    )

    assert output["missing_case_count"] == 1
    assert output["missing_cases"][0]["status"] == "failed_to_collect"
    assert output["not_submitted_count"] == 1
    assert output["not_submitted_cases"][0]["status"] == "not_submitted"


def test_filename_from_object_uri_extracts_custom_engine_path() -> None:
    filename = _filename_from_object_uri(
        object_uri=(
            "s3://orchestrator-artifacts/"
            "jobs/flow-123/attempt-1/"
            "engine/experiments/object_generation_sweeps/sweep/cases/case.json"
        ),
        flow_run_id="flow-123",
        attempt=1,
    )

    assert filename == "engine/experiments/object_generation_sweeps/sweep/cases/case.json"


def test_recover_remote_cases_uses_presign_get(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_read_engine_summary(flow_run_id: str):  # type: ignore[no-untyped-def]
        _ = flow_run_id
        return {
            "engine_manifest_uri": "s3://orchestrator-artifacts/jobs/flow-123/attempt-1/engine-artifacts.json",
            "attempt": 1,
        }

    monkeypatch.setattr(
        "infra.register.collect_object_generation_sweep._read_engine_summary",
        fake_read_engine_summary,
    )

    presign_calls: list[tuple[str, int, str]] = []

    def fake_presign_get_url(*, object_uri: str, flow_run_id: str, attempt: int, filename: str) -> str:
        _ = object_uri
        presign_calls.append((flow_run_id, attempt, filename))
        if filename == "engine-artifacts.json":
            return "https://signed.example/engine-artifacts.json"
        return "https://signed.example/case.json"

    def fake_fetch_json_url(url: str):  # type: ignore[no-untyped-def]
        if url.endswith("engine-artifacts.json"):
            return {
                "artifacts": [
                    {
                        "logical_name": "quality_case_json",
                        "object_uri": (
                            "s3://orchestrator-artifacts/jobs/flow-123/attempt-1/"
                            "engine/experiments/object_generation_sweeps/sweep/cases/case.json"
                        ),
                    }
                ]
            }
        if url.endswith("case.json"):
            return {
                "policy_id": "combo-001",
                "scenario_id": "scenario-001",
                "object_quality": {"summary": {"run_score": 0.5}},
            }
        return None

    monkeypatch.setattr(
        "infra.register.collect_object_generation_sweep._presign_get_url",
        fake_presign_get_url,
    )
    monkeypatch.setattr(
        "infra.register.collect_object_generation_sweep._fetch_json_url",
        fake_fetch_json_url,
    )
    monkeypatch.setattr(
        "infra.register.collect_object_generation_sweep._fetch_json_uri",
        lambda uri: None,
    )

    cases = _recover_remote_cases(
        [
            {
                "job_name": "job-1",
                "policy_id": "combo-001",
                "scenario_id": "scenario-001",
                "flow_run_id": "flow-123",
            }
        ]
    )

    assert len(cases) == 1
    assert cases[0]["policy_id"] == "combo-001"
    assert presign_calls == [
        ("flow-123", 1, "engine-artifacts.json"),
        (
            "flow-123",
            1,
            "engine/experiments/object_generation_sweeps/sweep/cases/case.json",
        ),
    ]


def test_load_env_file_populates_missing_values(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env.fixed"
    env_file.write_text(
        "CF_ACCESS_CLIENT_ID=cf-id\n"
        "CF_ACCESS_CLIENT_SECRET=cf-secret\n"
        "STORAGE_API_URL=https://storage-api.example\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("STORAGE_API_URL", raising=False)

    _load_env_file(env_file)

    assert __import__("os").environ["CF_ACCESS_CLIENT_ID"] == "cf-id"
    assert __import__("os").environ["CF_ACCESS_CLIENT_SECRET"] == "cf-secret"
    assert __import__("os").environ["STORAGE_API_URL"] == "https://storage-api.example"
