from __future__ import annotations

import json
from pathlib import Path

import pytest

from discoverex.config_loader import load_pipeline_config
from discoverex.execution_snapshot import build_execution_snapshot
from infra.prefect.artifacts import _settings_from_payload


def test_settings_from_payload_restores_worker_env_over_redacted_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("STORAGE_API_URL", "https://storage-api.discoverex.qzz.io")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://storage-api.discoverex.qzz.io/mlflow")
    cfg = load_pipeline_config(config_name="generate", config_dir="conf")
    snapshot = build_execution_snapshot(
        command="verify",
        args={"scene_json": "scene.json"},
        config_name="generate",
        config_dir="conf",
        overrides=[],
        config=cfg,
    )
    snapshot["resolved_settings"]["worker_http"]["cf_access_client_id"] = "***REDACTED***"
    snapshot["resolved_settings"]["worker_http"]["cf_access_client_secret"] = "***REDACTED***"
    snapshot["resolved_settings"]["storage"]["storage_api_url"] = "***REDACTED***"
    snapshot["resolved_settings"]["tracking"]["uri"] = "***REDACTED***"

    execution_config = tmp_path / "resolved_execution_config.json"
    execution_config.write_text(json.dumps(snapshot, ensure_ascii=True), encoding="utf-8")

    settings = _settings_from_payload({"execution_config": str(execution_config)})

    assert settings is not None
    assert settings.worker_http.cf_access_client_id == "cf-id"
    assert settings.worker_http.cf_access_client_secret == "cf-secret"
    assert settings.storage.storage_api_url == "https://storage-api.discoverex.qzz.io"
    assert settings.tracking.uri == "https://storage-api.discoverex.qzz.io/mlflow"
