from __future__ import annotations

from types import SimpleNamespace

from discoverex.application.flows.common import build_scene_payload


def test_build_scene_payload_includes_mlflow_run_id_when_present() -> None:
    scene = SimpleNamespace(
        meta=SimpleNamespace(
            scene_id="scene-1",
            version_id="v1",
            status=SimpleNamespace(value="approved"),
        ),
        verification=SimpleNamespace(final=SimpleNamespace(failure_reason=None)),
    )

    payload = build_scene_payload(
        scene,
        "/tmp/artifacts",
        "/tmp/artifacts/resolved_execution_config.json",
        "mlflow-run-123",
        "https://mlflow.example.com",
        "prefect-flow-123",
        "jobs/prefect-flow-123/attempt-1/",
    )

    assert payload["mlflow_run_id"] == "mlflow-run-123"
    assert payload["effective_tracking_uri"] == "https://mlflow.example.com"
    assert payload["flow_run_id"] == "prefect-flow-123"
    assert payload["artifact_prefix"] == "jobs/prefect-flow-123/attempt-1/"
