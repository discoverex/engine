from __future__ import annotations

from types import SimpleNamespace

from discoverex.application.flows.common import build_scene_payload


def test_build_scene_payload_includes_failure_reason_for_failed_scene() -> None:
    scene = SimpleNamespace(
        meta=SimpleNamespace(
            scene_id="scene-1", version_id="v1", status=SimpleNamespace(value="failed")
        ),
        verification=SimpleNamespace(
            final=SimpleNamespace(failure_reason="score_or_component_threshold_not_met")
        ),
    )

    payload = build_scene_payload(scene, artifacts_root="artifacts")

    assert payload["status"] == "failed"
    assert payload["failure_reason"] == "score_or_component_threshold_not_met"
    assert payload["scene_json"] == "artifacts/scenes/scene-1/v1/metadata/scene.json"


def test_build_scene_payload_includes_flow_identifiers() -> None:
    scene = SimpleNamespace(
        meta=SimpleNamespace(
            scene_id="scene-1", version_id="v1", status=SimpleNamespace(value="approved")
        ),
        verification=SimpleNamespace(final=SimpleNamespace(failure_reason=None)),
    )

    payload = build_scene_payload(
        scene,
        artifacts_root="artifacts",
        mlflow_run_id="mlflow-run-123",
        effective_tracking_uri="https://mlflow.example.com",
        flow_run_id="prefect-flow-123",
        artifact_prefix="jobs/prefect-flow-123/attempt-1/",
    )

    assert payload["mlflow_run_id"] == "mlflow-run-123"
    assert payload["effective_tracking_uri"] == "https://mlflow.example.com"
    assert payload["flow_run_id"] == "prefect-flow-123"
    assert payload["artifact_prefix"] == "jobs/prefect-flow-123/attempt-1/"
