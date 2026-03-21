from __future__ import annotations

import json
from urllib import request

import pytest

from discoverex.adapters.outbound.tracking.linkage import link_uploaded_artifacts
from discoverex.settings import AppSettings


def test_link_uploaded_artifacts_updates_remote_mlflow_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class _FakeResponse:
        def read(self) -> bytes:
            return b"{}"

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

    def _fake_urlopen(req: request.Request, timeout: int = 60) -> _FakeResponse:
        body = req.data.decode("utf-8") if isinstance(req.data, bytes) else ""
        calls.append((req.full_url, json.loads(body)))
        return _FakeResponse()

    monkeypatch.setattr(request, "urlopen", _fake_urlopen)
    result = link_uploaded_artifacts(
        payload={"mlflow_run_id": "run-123"},
        uploaded_uris={
            "stdout_uri": "s3://bucket/stdout.log",
            "result_uri": "s3://bucket/result.json",
            "engine_manifest_uri": "s3://bucket/engine-artifacts.json",
        },
        engine_mlflow_tags={
            "artifact_scene_uri": "s3://bucket/scenes/scene.json",
        },
        settings=AppSettings.model_validate(
            {
                "pipeline": {
                    "models": {
                        "background_generator": {"target": "pkg.Background"},
                        "background_upscaler": {"target": "pkg.Upscaler"},
                        "object_generator": {"target": "pkg.Object"},
                        "hidden_region": {"target": "pkg.Hidden"},
                        "inpaint": {"target": "pkg.Inpaint"},
                        "perception": {"target": "pkg.Perception"},
                        "fx": {"target": "pkg.Fx"},
                    },
                    "adapters": {
                        "artifact_store": {"target": "pkg.Artifacts"},
                        "metadata_store": {"target": "pkg.Metadata"},
                        "tracker": {"target": "pkg.Tracker"},
                        "scene_io": {"target": "pkg.SceneIo"},
                        "report_writer": {"target": "pkg.ReportWriter"},
                    },
                    "runtime": {},
                    "thresholds": {},
                    "model_versions": {},
                },
                "tracking": {"uri": "https://mlflow.example.com"},
                "storage": {},
                "worker_http": {
                    "cf_access_client_id": "cf-id",
                    "cf_access_client_secret": "cf-secret",
                },
                "runtime_paths": {},
                "execution": {
                    "config_name": "generate",
                    "config_dir": "conf",
                },
            }
        ),
    )

    assert result.status == "linked"
    assert result.linked_tags == {
        "artifact_engine_manifest_uri": "s3://bucket/engine-artifacts.json",
        "artifact_result_uri": "s3://bucket/result.json",
        "artifact_scene_uri": "s3://bucket/scenes/scene.json",
        "artifact_stdout_uri": "s3://bucket/stdout.log",
    }
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == [
        "set-tag",
        "set-tag",
        "set-tag",
        "set-tag",
    ]
    assert calls[0][1]["run_id"] == "run-123"


def test_link_uploaded_artifacts_skips_without_mlflow_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = link_uploaded_artifacts(
        payload={},
        uploaded_uris={"stdout_uri": "s3://bucket/stdout.log"},
        engine_mlflow_tags={},
    )

    assert result.status == "skipped_missing_run_id"
    assert result.linked_tags == {}
