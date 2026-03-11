from __future__ import annotations

from typing import cast

from typer.testing import CliRunner

from discoverex.adapters.inbound.cli.main import app


def test_gen_verify_legacy_emits_deprecation_warning(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    def _fake_run_command(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "scene_id": "s1",
            "version_id": "v1",
            "status": "approved",
            "scene_json": "artifacts/scenes/s1/v1/scene.json",
        }

    monkeypatch.setattr(
        "discoverex.adapters.inbound.cli.main._run_command",
        _fake_run_command,
    )

    result = runner.invoke(app, ["gen-verify", "--background-asset-ref", "bg://d"])
    assert result.exit_code == 0
    assert "is deprecated; use 'generate'" in result.stderr


def test_verify_only_legacy_emits_deprecation_warning(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    def _fake_run_command(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "scene_id": "s1",
            "version_id": "v1",
            "status": "approved",
            "scene_json": "artifacts/scenes/s1/v1/scene.json",
        }

    monkeypatch.setattr(
        "discoverex.adapters.inbound.cli.main._run_command",
        _fake_run_command,
    )

    result = runner.invoke(app, ["verify-only", "--scene-json", "/tmp/s.json"])
    assert result.exit_code == 0
    assert "is deprecated; use 'verify'" in result.stderr


def test_generate_accepts_background_prompt_and_object_prompt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run_command(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {
            "scene_id": "s1",
            "version_id": "v1",
            "status": "approved",
            "scene_json": "artifacts/scenes/s1/v1/scene.json",
        }

    monkeypatch.setattr(
        "discoverex.adapters.inbound.cli.main._run_command",
        _fake_run_command,
    )

    result = runner.invoke(
        app,
        [
            "generate",
            "--background-prompt",
            "foggy alley",
            "--object-prompt",
            "hidden blue key",
        ],
    )
    assert result.exit_code == 0
    assert captured["args"] == {
        "background_prompt": "foggy alley",
        "object_prompt": "hidden blue key",
    }


def test_generate_accepts_final_prompt(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()
    captured: dict[str, object] = {}

    def _fake_run_command(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {
            "scene_id": "s1",
            "version_id": "v1",
            "status": "approved",
            "scene_json": "artifacts/scenes/s1/v1/scene.json",
        }

    monkeypatch.setattr(
        "discoverex.adapters.inbound.cli.main._run_command",
        _fake_run_command,
    )
    result = runner.invoke(
        app,
        [
            "generate",
            "--background-prompt",
            "foggy alley",
            "--final-prompt",
            "polished render",
        ],
    )
    assert result.exit_code == 0
    captured_args = cast(dict[str, object], captured["args"])
    assert captured_args["final_prompt"] == "polished render"
