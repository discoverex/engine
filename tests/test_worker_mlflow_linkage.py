from __future__ import annotations

import json
from urllib import request

import pytest

from discoverex.orchestrator_contract.uploads.mlflow_tags import link_uploaded_artifacts


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
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-secret")

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
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://mlflow.example.com")

    result = link_uploaded_artifacts(
        payload={},
        uploaded_uris={"stdout_uri": "s3://bucket/stdout.log"},
        engine_mlflow_tags={},
    )

    assert result.status == "skipped_missing_run_id"
    assert result.linked_tags == {}
