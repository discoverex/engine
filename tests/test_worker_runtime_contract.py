from __future__ import annotations

import json
from pathlib import Path

import pytest

from discoverex.config_loader import load_pipeline_config
from discoverex.orchestrator_contract.artifacts import (
    ARTIFACT_DIR_ENV,
    ARTIFACT_MANIFEST_ENV,
)
from discoverex.orchestrator_contract.worker_runtime import (
    normalize_pipeline_config_for_worker_runtime,
    write_worker_artifact_manifest,
)


def test_normalize_pipeline_config_for_worker_runtime_preserves_selected_adapters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ARTIFACT_DIR_ENV, str(tmp_path / "engine-artifacts"))
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=[
            "adapters/artifact_store=minio",
            "adapters/tracker=mlflow_server",
            "adapters/metadata_store=postgres",
        ],
    )

    normalized = normalize_pipeline_config_for_worker_runtime(cfg)

    assert normalized.runtime.artifacts_root == str(
        (tmp_path / "engine-artifacts").resolve()
    )
    assert normalized.adapters.artifact_store.target.endswith(
        "MinioArtifactStoreAdapter"
    )
    assert normalized.adapters.metadata_store.target.endswith(
        "PostgresMetadataStoreAdapter"
    )
    assert normalized.adapters.tracker.target.endswith("MLflowTrackerAdapter")
    assert normalized.adapters.report_writer.target.endswith("JsonReportWriterAdapter")


def test_write_worker_artifact_manifest_collects_files_under_worker_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "engine"
    manifest_path = tmp_path / "engine-artifacts.json"
    saved_dir = artifact_root / "scenes" / "scene-1" / "version-1" / "metadata"
    saved_dir.mkdir(parents=True)
    scene_path = saved_dir / "scene.json"
    verification_path = saved_dir / "verification.json"
    naturalness_path = saved_dir / "naturalness.json"
    lottie_path = (
        artifact_root
        / "scenes"
        / "scene-1"
        / "version-1"
        / "outputs"
        / "animation.lottie"
    )
    lottie_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text("{}", encoding="utf-8")
    verification_path.write_text("{}", encoding="utf-8")
    naturalness_path.write_text("{}", encoding="utf-8")
    lottie_path.write_bytes(b"PK")
    outside_path = tmp_path / "outside.json"
    outside_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(ARTIFACT_DIR_ENV, str(artifact_root))
    monkeypatch.setenv(ARTIFACT_MANIFEST_ENV, str(manifest_path))

    written = write_worker_artifact_manifest(
        artifacts_root=artifact_root,
        artifacts=[
            ("scene", scene_path),
            ("verification", verification_path),
            ("naturalness", naturalness_path),
            ("lottie", lottie_path),
            ("outside", outside_path),
        ],
    )

    assert written == manifest_path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["artifacts"] == [
        {
            "logical_name": "scene_json",
            "relative_path": "scenes/scene-1/version-1/metadata/scene.json",
            "content_type": "application/json",
            "mlflow_tag": "artifact_scene_uri",
            "description": None,
        },
        {
            "logical_name": "verification_json",
            "relative_path": "scenes/scene-1/version-1/metadata/verification.json",
            "content_type": "application/json",
            "mlflow_tag": "artifact_verification_uri",
            "description": None,
        },
        {
            "logical_name": "naturalness_json",
            "relative_path": "scenes/scene-1/version-1/metadata/naturalness.json",
            "content_type": "application/json",
            "mlflow_tag": "artifact_naturalness_uri",
            "description": None,
        },
        {
            "logical_name": "lottie_bundle",
            "relative_path": "scenes/scene-1/version-1/outputs/animation.lottie",
            "content_type": "application/zip",
            "mlflow_tag": "artifact_lottie_uri",
            "description": None,
        },
    ]
    assert (
        artifact_root / "scenes" / "scene-1" / "version-1" / "metadata" / "scene.json"
    ).read_text(encoding="utf-8") == "{}"
    assert (
        artifact_root
        / "scenes"
        / "scene-1"
        / "version-1"
        / "metadata"
        / "verification.json"
    ).read_text(encoding="utf-8") == "{}"
    assert (
        artifact_root
        / "scenes"
        / "scene-1"
        / "version-1"
        / "metadata"
        / "naturalness.json"
    ).read_text(encoding="utf-8") == "{}"
