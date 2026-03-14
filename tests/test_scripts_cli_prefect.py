from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from scripts.cli.prefect import (
    DEFAULT_REGISTER_JOB_SPEC,
    app,
)


def test_register_defaults_to_standard_job_spec(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(app, ["register", "--branch", "dev"])

    assert result.exit_code == 0
    assert captured["script_name"] == "submit_job_spec.py"
    assert captured["args"] == [
        "--deployment",
        "discoverex-combined-dev",
        "--job-spec-file",
        str(DEFAULT_REGISTER_JOB_SPEC),
    ]


def test_register_requires_branch(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    def _fake_run(script_name: str, args: list[str]) -> int:
        _ = (script_name, args)
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(app, ["register"])

    assert result.exit_code == 2
    assert "--branch is required" in result.stdout


def test_register_forwards_submit_spec_args(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(
        app,
        [
            "register",
            "--branch",
            "feature/foo",
            "--job-name",
            "manual-run",
        ],
    )

    assert result.exit_code == 0
    assert captured["script_name"] == "submit_job_spec.py"
    assert captured["args"] == [
        "--deployment",
        "discoverex-combined-feature-foo",
        "--job-name",
        "manual-run",
        "--job-spec-file",
        str(DEFAULT_REGISTER_JOB_SPEC),
    ]


def test_register_maps_command_to_flow_kind(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(
        app,
        [
            "register",
            "--branch",
            "feature/foo",
            "--command",
            "verify",
            "--job-name",
            "manual-run",
        ],
    )

    assert result.exit_code == 0
    assert captured["script_name"] == "submit_job_spec.py"
    assert captured["args"] == [
        "--deployment",
        "discoverex-verify-feature-foo",
        "--command",
        "verify",
        "--job-name",
        "manual-run",
        "--job-spec-file",
        str(DEFAULT_REGISTER_JOB_SPEC),
    ]


def test_register_flow_targets_named_flow_kind(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(app, ["register-flow", "generate", "--branch", "dev"])

    assert result.exit_code == 0
    assert captured["script_name"] == "submit_job_spec.py"
    assert captured["args"] == [
        "--deployment",
        "discoverex-generate-dev",
        "--job-spec-file",
        str(DEFAULT_REGISTER_JOB_SPEC),
    ]


def test_default_register_job_spec_points_to_repo_standard_file() -> None:
    assert DEFAULT_REGISTER_JOB_SPEC == (
        Path(__file__).resolve().parents[1]
        / "infra"
        / "register"
        / "job_specs"
        / "real-generate-sdxl-gpu-8gb.json"
    )
