from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from typer.testing import CliRunner

from scripts.cli.prefect import (
    DEFAULT_EXPERIMENT_NAME,
    DEFAULT_EXPERIMENT_QUEUE,
    DEFAULT_NATURALNESS_SWEEP_SPEC,
    DEFAULT_REGISTER_JOB_SPEC,
    _build_job_spec_json_for_row,
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

    result = runner.invoke(app, ["registercombined", "--branch", "dev"])

    assert result.exit_code == 0
    assert captured["script_name"] == "infra.register.submit_job_spec"
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

    result = runner.invoke(app, ["registercombined"])

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
            "registercombined",
            "--branch",
            "feature/foo",
            "--job-name",
            "manual-run",
        ],
    )

    assert result.exit_code == 0
    assert captured["script_name"] == "infra.register.submit_job_spec"
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
            "registercombined",
            "--branch",
            "feature/foo",
            "--command",
            "verify",
            "--job-name",
            "manual-run",
        ],
    )

    assert result.exit_code == 0
    assert captured["script_name"] == "infra.register.submit_job_spec"
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

    result = runner.invoke(app, ["register", "flow", "generate", "--branch", "dev"])

    assert result.exit_code == 0
    assert captured["script_name"] == "infra.register.submit_job_spec"
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
        / "real-generate-pixart-hidden-object-naturalness-v2-8gb-safe.yaml"
    )


def test_build_prefect_log_filter_targets_flow_run_id() -> None:
    flow_run_id = "f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c"
    log_filter = _build_prefect_log_filter(flow_run_id)
    assert log_filter.flow_run_id.any_ == [UUID(flow_run_id)]


def test_build_job_spec_json_for_row_overrides_prompts() -> None:
    payload = _build_job_spec_json_for_row(
        {
            "job_name": "template-name",
            "inputs": {
                "args": {
                    "background_prompt": "old-bg",
                    "background_negative_prompt": "old-bg-neg",
                    "object_prompt": "old-object",
                    "object_negative_prompt": "old-object-neg",
                    "final_prompt": "old-final",
                    "final_negative_prompt": "old-final-neg",
                }
            },
        },
        {
            "job_name": "scene-001",
            "background_prompt": "harbor",
            "background_negative_prompt": "",
            "object_prompt": "banana",
            "object_negative_prompt": "bad object",
            "final_prompt": "",
            "final_negative_prompt": "",
        },
        row_index=1,
    )

    assert '"job_name": "scene-001"' in payload
    assert '"background_prompt": "harbor"' in payload
    assert '"background_negative_prompt": "old-bg-neg"' in payload
    assert '"object_prompt": "banana"' in payload
    assert '"object_negative_prompt": "bad object"' in payload
    assert '"final_prompt": "old-final"' in payload
    assert '"final_negative_prompt": "old-final-neg"' in payload


def test_register_batch_submits_one_run_per_csv_row(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: list[list[str]] = []
    csv_path = tmp_path / "scenes.csv"
    csv_path.write_text(
        "job_name,background_prompt,object_prompt,final_prompt\n"
        "scene-1,harbor,banana,polished harbor\n"
        "scene-2,attic,key,polished attic\n",
        encoding="utf-8",
    )

    def _fake_run(script_name: str, args: list[str]) -> int:
        assert script_name == "infra.register.submit_job_spec"
        captured.append(args)
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(
        app,
        ["register", "batch", str(csv_path), "--branch", "dev"],
    )

    assert result.exit_code == 0
    assert len(captured) == 2
    assert captured[0][0:2] == ["--deployment", "discoverex-generate-dev"]
    assert captured[1][0:2] == ["--deployment", "discoverex-generate-dev"]
    assert '"job_name": "scene-1"' in captured[0][-1]
    assert '"background_prompt": "harbor"' in captured[0][-1]
    assert '"object_prompt": "banana"' in captured[0][-1]
    assert '"final_prompt": "polished harbor"' in captured[0][-1]
    assert '"job_name": "scene-2"' in captured[1][-1]
    assert '"background_prompt": "attic"' in captured[1][-1]
    assert '"object_prompt": "key"' in captured[1][-1]
    assert '"final_prompt": "polished attic"' in captured[1][-1]


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
                timestamp=SimpleNamespace(strftime=lambda fmt: "2026-03-15 01:23:45"),
            )
        ]

    monkeypatch.setattr(
        "scripts.cli.prefect._read_prefect_logs", _fake_read_prefect_logs
    )

    import asyncio

    flow_run_id = "f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c"
    asyncio.run(
        __import__("scripts.cli.prefect", fromlist=["_fetch_logs"])._fetch_logs(
            flow_run_id, 25
        )
    )

    output = capsys.readouterr().out
    assert "hello" in output
    assert "prefect.flow_runs | INFO" in output


def test_inspect_run_renders_tree(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    async def _fake_describe(flow_run_id: str, depth: int) -> list[str]:
        assert flow_run_id == "f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c"
        assert depth == 3
        return [
            "flow discoverex-generate-flow [Completed] id=root tasks=1",
            "  task discoverex-generate-pipeline-0 [Completed] id=task-1 child_flow=child-1",
            "    flow discoverex-generate-pipeline [Completed] id=child-1 tasks=11",
        ]

    monkeypatch.setattr("scripts.cli.prefect._describe_flow_run_tree", _fake_describe)

    result = runner.invoke(
        app,
        ["inspect-run", "f7b6ec0c-48e1-4dcc-8e74-1f03b3bbdd9c", "--depth", "3"],
    )

    assert result.exit_code == 0
    assert "flow discoverex-generate-flow" in result.stdout
    assert "task discoverex-generate-pipeline-0" in result.stdout
    assert "flow discoverex-generate-pipeline" in result.stdout


def test_register_experiment_sweep_invokes_script(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(app, ["register", "experiment-sweep"])

    assert result.exit_code == 0
    assert captured["script_name"] == "infra.register.naturalness_sweep"
    assert captured["args"] == [
        str(DEFAULT_NATURALNESS_SWEEP_SPEC),
        "--experiment",
        DEFAULT_EXPERIMENT_NAME,
    ]


def test_register_experiment_sweep_uses_experiment_deployment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
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
            "experiment-sweep",
            "--experiment",
            "naturalness",
            "--branch",
            "dev",
        ],
    )

    assert result.exit_code == 0
    assert captured["script_name"] == "infra.register.naturalness_sweep"
    assert captured["args"] == [
        str(DEFAULT_NATURALNESS_SWEEP_SPEC),
        "--deployment",
        "discoverex-naturalness-experiment-dev",
        "--branch",
        "dev",
        "--experiment",
        "naturalness",
    ]


def test_deploy_experiment_uses_batch_queue(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run(script_name: str, args: list[str]) -> int:
        captured["script_name"] = script_name
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.prefect._run_infra_script", _fake_run)

    result = runner.invoke(
        app, ["deploy", "experiment", "--experiment", "naturalness", "--branch", "dev"]
    )

    assert result.exit_code == 0
    assert captured["script_name"] == "infra.register.deploy_prefect_flows"
    assert captured["args"] == [
        "--flow-kind",
        "generate",
        "--work-queue-name",
        DEFAULT_EXPERIMENT_QUEUE,
        "--deployment-name",
        "discoverex-naturalness-experiment-dev",
        "--branch",
        "dev",
    ]
