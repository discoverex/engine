from __future__ import annotations

import json
from pathlib import Path

import pytest

from discoverex.orchestrator_contract import (
    ARTIFACT_DIR_ENV,
    ARTIFACT_MANIFEST_ENV,
    write_engine_artifact_manifest,
)


def test_write_engine_artifact_manifest_writes_canonical_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "engine"
    artifact_root.mkdir()
    manifest_path = tmp_path / "engine-artifacts.json"
    scene_path = artifact_root / "scene" / "scene.json"
    scene_path.parent.mkdir(parents=True)
    scene_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(ARTIFACT_DIR_ENV, str(artifact_root))
    monkeypatch.setenv(ARTIFACT_MANIFEST_ENV, str(manifest_path))

    written = write_engine_artifact_manifest(
        [
            {
                "logical_name": "scene",
                "relative_path": "scene/scene.json",
                "content_type": "application/json",
                "mlflow_tag": "artifact_scene_uri",
            }
        ]
    )

    assert written == manifest_path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["artifacts"][0]["relative_path"] == "scene/scene.json"


def test_write_engine_artifact_manifest_returns_none_for_empty_artifacts() -> None:
    assert write_engine_artifact_manifest([]) is None


def test_write_engine_artifact_manifest_rejects_paths_outside_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "engine"
    artifact_root.mkdir()
    monkeypatch.setenv(ARTIFACT_DIR_ENV, str(artifact_root))
    monkeypatch.setenv(ARTIFACT_MANIFEST_ENV, str(tmp_path / "engine-artifacts.json"))

    with pytest.raises(RuntimeError, match="stay under artifact root"):
        write_engine_artifact_manifest(
            [{"logical_name": "scene", "relative_path": "../scene.json"}]
        )
