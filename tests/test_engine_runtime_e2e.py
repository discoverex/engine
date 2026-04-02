from __future__ import annotations

from pathlib import Path

import pytest

from infra.e2e.engine_runtime_e2e import (
    run_tracking_artifact_e2e,
    run_worker_contract_e2e,
)


def test_tracking_artifact_e2e_generates_scene_and_records_tracking(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    pytest.importorskip("mlflow")

    summary = run_tracking_artifact_e2e(work_dir=tmp_path)

    assert Path(summary.scene_json).exists()
    assert Path(summary.verification_json).exists()
    assert Path(summary.execution_config).exists()
    assert summary.extra["mlflow_params"]["scene_id"] == summary.scene_id
    assert summary.extra["mlflow_params"]["version_id"] == summary.version_id
    assert "metadata/prompt_bundle.json" in summary.extra["mlflow_artifacts"]
    assert "resolved_execution_config.json" in summary.extra["mlflow_artifacts"]
    assert (
        f"scenes/{summary.scene_id}/{summary.version_id}/metadata/scene.json"
        in summary.extra["bucket_objects"]
    )


def test_worker_contract_e2e_uploads_engine_manifest_and_scene(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    pytest.importorskip("mlflow")

    summary = run_worker_contract_e2e(work_dir=tmp_path)

    uploaded = summary.extra["uploaded"]
    manifest = summary.extra["uploaded_manifest"]
    assert Path(summary.scene_json).exists()
    assert Path(summary.verification_json).exists()
    assert Path(summary.execution_config).exists()
    assert uploaded["engine_manifest_uri"].endswith("/engine-artifacts.json")
    assert uploaded["engine_artifact_uris"]["scene_json"].endswith(
        f"/scenes/{summary.scene_id}/{summary.version_id}/metadata/scene.json"
    )
    assert uploaded["engine_artifact_uris"]["verification_json"].endswith(
        f"/scenes/{summary.scene_id}/{summary.version_id}/metadata/verification.json"
    )
    logical_names = {item["logical_name"] for item in manifest["artifacts"]}
    assert "scene_json" in logical_names
    assert "verification_json" in logical_names
    assert "engine-artifacts.json" in "\n".join(summary.extra["uploaded_objects"])
