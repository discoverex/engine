from __future__ import annotations

from typer.testing import CliRunner

from discoverex.adapters.inbound.cli.main import app


def test_gen_verify_legacy_emits_deprecation_warning(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    def _fake_run_engine_entry(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "scene_id": "s1",
            "version_id": "v1",
            "status": "approved",
            "scene_json": "artifacts/scenes/s1/v1/scene.json",
        }

    monkeypatch.setattr(
        "discoverex.adapters.inbound.cli.main.run_engine_entry",
        _fake_run_engine_entry,
    )

    result = runner.invoke(app, ["gen-verify", "--background-asset-ref", "bg://d"])
    assert result.exit_code == 0
    assert "is deprecated; use 'generate'" in result.stderr


def test_verify_only_legacy_emits_deprecation_warning(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    runner = CliRunner()

    def _fake_run_engine_entry(**_kwargs):  # type: ignore[no-untyped-def]
        return {
            "scene_id": "s1",
            "version_id": "v1",
            "status": "approved",
            "scene_json": "artifacts/scenes/s1/v1/scene.json",
        }

    monkeypatch.setattr(
        "discoverex.adapters.inbound.cli.main.run_engine_entry",
        _fake_run_engine_entry,
    )

    result = runner.invoke(app, ["verify-only", "--scene-json", "/tmp/s.json"])
    assert result.exit_code == 0
    assert "is deprecated; use 'verify'" in result.stderr
