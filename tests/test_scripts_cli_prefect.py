from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from typer.testing import CliRunner

from scripts.cli.prefect import (
    DEFAULT_REGISTER_JOB_SPEC,
    _build_prefect_log_filter,
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


def test_build_prefect_log_filter_targets_flow_run_id() -> None:
    flow_run_id = "f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c"
    log_filter = _build_prefect_log_filter(flow_run_id)
    assert log_filter.flow_run_id.any_ == [UUID(flow_run_id)]


def test_fetch_logs_formats_output(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setitem(
        __import__("sys").modules,
        "prefect.logging.configuration",
        SimpleNamespace(setup_logging=lambda: None),
    )

    async def _fake_read_prefect_logs(flow_run_id: str, limit: int) -> list[object]:
        assert flow_run_id == "f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c"
        assert limit == 25
        return [
            SimpleNamespace(
                level=20,
                level_name="INFO",
                name="prefect.flow_runs",
                message="hello",
                timestamp=SimpleNamespace(
                    strftime=lambda fmt: "2026-03-15 01:23:45"
                ),
            )
        ]

    monkeypatch.setattr("scripts.cli.prefect._read_prefect_logs", _fake_read_prefect_logs)

    import asyncio

    flow_run_id = "f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c"
    asyncio.run(__import__("scripts.cli.prefect", fromlist=["_fetch_logs"])._fetch_logs(flow_run_id, 25))

    output = capsys.readouterr().out
    assert "hello" in output
    assert "prefect.flow_runs | INFO" in output
