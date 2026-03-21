from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from scripts.cli.worker import app


def test_worker_fixed_up_invokes_compose_with_build(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    monkeypatch.setattr("scripts.cli.worker.REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.cli.worker.WORKER_DIR", tmp_path / "infra" / "worker"
    )
    monkeypatch.setattr(
        "scripts.cli.worker.FIXED_ENV", tmp_path / "infra" / "worker" / ".env.fixed"
    )
    monkeypatch.setattr(
        "scripts.cli.worker.FIXED_COMPOSE",
        tmp_path / "infra" / "worker" / "docker-compose.fixed.yml",
    )

    def _fake_compose_fixed(args: list[str]) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.worker._compose_fixed", _fake_compose_fixed)

    result = runner.invoke(app, ["fixed", "up"])

    assert result.exit_code == 0
    assert captured["args"] == ["up", "-d", "--build"]
    assert (tmp_path / "runtime" / "worker" / "cache").exists()
    assert (tmp_path / "runtime" / "worker" / "checkpoints").exists()


def test_worker_fixed_up_uses_runtime_dir_from_env_file(
    monkeypatch, tmp_path: Path
) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    env_file = tmp_path / "infra" / "worker" / ".env.fixed"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("WORKER_RUNTIME_DIR=mounted/runtime\n", encoding="utf-8")

    monkeypatch.setattr("scripts.cli.worker.REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "scripts.cli.worker.WORKER_DIR", tmp_path / "infra" / "worker"
    )
    monkeypatch.setattr("scripts.cli.worker.FIXED_ENV", env_file)
    monkeypatch.setattr(
        "scripts.cli.worker.FIXED_COMPOSE",
        tmp_path / "infra" / "worker" / "docker-compose.fixed.yml",
    )

    def _fake_compose_fixed(args: list[str]) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.worker._compose_fixed", _fake_compose_fixed)

    result = runner.invoke(app, ["fixed", "up"])

    assert result.exit_code == 0
    assert captured["args"] == ["up", "-d", "--build"]
    assert (tmp_path / "mounted" / "runtime" / "cache").exists()
    assert (tmp_path / "mounted" / "runtime" / "checkpoints").exists()


def test_worker_fixed_logs_forwards_tail(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_compose_fixed(args: list[str]) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.worker._compose_fixed", _fake_compose_fixed)

    result = runner.invoke(app, ["fixed", "logs", "--tail", "50"])

    assert result.exit_code == 0
    assert captured["args"] == ["logs", "--tail=50"]


def test_worker_fixed_logs_forwards_follow(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_compose_fixed(args: list[str]) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr("scripts.cli.worker._compose_fixed", _fake_compose_fixed)

    result = runner.invoke(app, ["fixed", "logs", "--tail", "50", "-f"])

    assert result.exit_code == 0
    assert captured["args"] == ["logs", "--tail=50", "-f"]
