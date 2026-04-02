from __future__ import annotations

import json
from pathlib import Path

import pytest

from discoverex.config_loader import load_pipeline_config
from discoverex.execution_snapshot import build_execution_snapshot
from infra.prefect.artifacts import _settings_from_payload


def test_settings_from_payload_reuses_snapshot_without_env_override(
    tmp_path: Path,
) -> None:
    cfg = load_pipeline_config(config_name="generate", config_dir="conf")
    snapshot = build_execution_snapshot(
        command="verify",
        args={"scene_json": "scene.json"},
        config_name="generate",
        config_dir="conf",
        overrides=[],
        config=cfg,
    )
    execution_config = tmp_path / "resolved_execution_config.json"
    execution_config.write_text(json.dumps(snapshot, ensure_ascii=True), encoding="utf-8")

    settings = _settings_from_payload({"execution_config": str(execution_config)})

    assert settings is not None
    assert settings.model_dump(mode="python") == snapshot["resolved_settings"]
