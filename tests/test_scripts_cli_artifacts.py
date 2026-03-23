from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from scripts.cli.artifacts import _composite_uri_for_run, _parse_s3_uri, _run_tags
from scripts.cli.artifacts import app


def test_experiment_by_name_prints_experiment(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    monkeypatch.setattr(
        "scripts.cli.artifacts._get_experiment_by_name",
        lambda env, name: {  # noqa: ARG005
            "experiment_id": "42",
            "name": name,
            "lifecycle_stage": "active",
        },
    )

    result = runner.invoke(
        app,
        [
            "experiment-by-name",
            "--experiment-name",
            "single-object-debug",
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["found"] is True
    assert payload["experiment"]["experiment_id"] == "42"


def test_experiment_by_name_exits_when_missing(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    monkeypatch.setattr(
        "scripts.cli.artifacts._get_experiment_by_name",
        lambda env, name: None,  # noqa: ARG005
    )

    result = runner.invoke(
        app,
        [
            "experiment-by-name",
            "--experiment-name",
            "missing-experiment",
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["found"] is False


def test_runs_search_resolves_experiment_name(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    monkeypatch.setattr(
        "scripts.cli.artifacts._get_experiment_by_name",
        lambda env, name: {  # noqa: ARG005
            "experiment_id": "55",
            "name": name,
        },
    )
    monkeypatch.setattr(
        "scripts.cli.artifacts._search_runs",
        lambda env, experiment_ids, filter_string: [  # noqa: ARG005
            {
                "info": {
                    "run_id": "run-1",
                    "status": "FINISHED",
                    "artifact_uri": "s3://bucket/run-1",
                },
                "data": {
                    "tags": [
                        {"key": "mlflow.runName", "value": "combo-001"},
                        {"key": "job_name", "value": "single-object-debug-001"},
                    ]
                },
            }
        ],
    )

    result = runner.invoke(
        app,
        [
            "runs-search",
            "--experiment-name",
            "single-object-debug",
            "--filter",
            "tags.job_name = 'single-object-debug-001'",
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["experiment_ids"] == ["55"]
    assert payload["run_count"] == 1
    assert payload["runs"][0]["run_id"] == "run-1"
    assert payload["runs"][0]["run_name"] == "combo-001"


def test_runs_search_requires_target(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "runs-search",
            "--env-file",
            str(tmp_path / "missing.env"),
        ],
    )
    assert result.exit_code == 2


def test_parse_s3_uri_splits_bucket_and_key() -> None:
    bucket, key = _parse_s3_uri("s3://discoverex-artifacts/jobs/run-1/attempt-1/file.png")
    assert bucket == "discoverex-artifacts"
    assert key == "jobs/run-1/attempt-1/file.png"


def test_run_tags_flattens_mlflow_tag_entries() -> None:
    run = {
        "data": {
            "tags": [
                {"key": "artifact_composite_uri", "value": "s3://bucket/composite.png"},
                {"key": "artifact_output_manifest_uri", "value": "s3://bucket/manifest.json"},
            ]
        }
    }
    tags = _run_tags(run)
    assert tags["artifact_composite_uri"] == "s3://bucket/composite.png"
    assert tags["artifact_output_manifest_uri"] == "s3://bucket/manifest.json"


def test_composite_uri_prefers_direct_tag() -> None:
    tags = {"artifact_composite_uri": "s3://bucket/composite.png"}
    assert _composite_uri_for_run({}, tags) == "s3://bucket/composite.png"
