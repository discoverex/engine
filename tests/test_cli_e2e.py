from __future__ import annotations

from typer.testing import CliRunner

from discoverex.adapters.inbound.cli.main import app


def test_e2e_command_runs_requested_scenario(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_e2e(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {"tracking-artifact": {"scenario": "tracking-artifact"}}

    monkeypatch.setattr("discoverex.adapters.inbound.cli.main._run_e2e", fake_run_e2e)

    result = runner.invoke(
        app,
        [
            "e2e",
            "--scenario",
            "tracking-artifact",
            "--model-group",
            "tiny_torch",
            "--work-dir",
            "/tmp/discoverex-e2e",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "scenario": "tracking-artifact",
        "model_group": "tiny_torch",
        "work_dir": "/tmp/discoverex-e2e",
        "ensure_live_infra": False,
    }
    assert '"tracking-artifact"' in result.stdout


def test_e2e_command_rejects_unknown_scenario() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["e2e", "--scenario", "weird"])

    assert result.exit_code == 2
    assert "scenario must be one of" in result.stderr
