from __future__ import annotations

import json
from pathlib import Path

from discoverex.config_loader import load_pipeline_config
from discoverex.execution_snapshot import (
    build_execution_snapshot,
    build_tracking_params,
    write_execution_snapshot,
)


def test_execution_snapshot_redacts_sensitive_values(monkeypatch) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")
    cfg = load_pipeline_config(config_name="generate", config_dir="conf")

    snapshot = build_execution_snapshot(
        command="generate",
        args={"background_asset_ref": "bg://dummy"},
        config_name="generate",
        config_dir="conf",
        overrides=["adapters/tracker=mlflow_server"],
        config=cfg,
    )

    assert snapshot["runtime_env"]["MLFLOW_TRACKING_URI"] == "***REDACTED***"
    resolved = snapshot["resolved_config"]
    assert resolved["runtime"]["env"]["tracking_uri"] == "***REDACTED***"


def test_execution_snapshot_writes_json_and_flattens_tracking_params(
    tmp_path: Path,
) -> None:
    cfg = load_pipeline_config(config_name="generate", config_dir="conf")
    snapshot = build_execution_snapshot(
        command="generate",
        args={"background_asset_ref": "bg://dummy"},
        config_name="generate",
        config_dir="conf",
        overrides=[],
        config=cfg,
    )

    path = write_execution_snapshot(
        artifacts_root=tmp_path,
        command="generate",
        snapshot=snapshot,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    params = build_tracking_params(payload)
    assert path.name == "resolved_execution_config.json"
    assert params["command"] == "generate"
    assert params["config_name"] == "generate"
    assert "adapters.tracker" in params
