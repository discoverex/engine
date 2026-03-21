from __future__ import annotations

import sys
from pathlib import Path
from urllib import request
from urllib.parse import parse_qs, urlsplit

import pytest

from discoverex.adapters.outbound.tracking.mlflow import MLflowTrackerAdapter


class _FakeRun:
    def __init__(self, run_id: str = "run-123") -> None:
        self.info = type("_Info", (), {"run_id": run_id})()

    def __enter__(self) -> "_FakeRun":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        _ = (exc_type, exc, tb)


class _FakeMLflow:
    def __init__(self) -> None:
        self.tracking_uri = ""
        self.experiment_name = ""
        self.logged_params: list[dict[str, object]] = []
        self.logged_metrics: list[dict[str, float]] = []
        self.logged_artifacts: list[str] = []
        self.tags: dict[str, str] = {}

    def set_tracking_uri(self, tracking_uri: str) -> None:
        self.tracking_uri = tracking_uri

    def set_experiment(self, experiment_name: str) -> None:
        self.experiment_name = experiment_name

    def start_run(self, run_name: str) -> _FakeRun:
        self.tags["run_name"] = run_name
        return _FakeRun()

    def log_params(self, params: dict[str, object]) -> None:
        self.logged_params.append(params)

    def log_metrics(self, metrics: dict[str, float]) -> None:
        self.logged_metrics.append(metrics)

    def log_artifact(self, artifact: str) -> None:
        self.logged_artifacts.append(artifact)

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value


def test_mlflow_tracker_logs_artifacts_for_local_tracking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeMLflow()
    monkeypatch.setitem(sys.modules, "mlflow", fake)

    artifact = tmp_path / "scene.json"
    artifact.write_text("{}", encoding="utf-8")
    tracker = MLflowTrackerAdapter(tracking_uri="sqlite:///mlflow.db")
    run_id = tracker.log_pipeline_run(
        run_name="generate",
        params={"scene_id": "scene-1", "version_id": "ver-1"},
        metrics={"pass": 1.0},
        artifacts=[artifact],
    )

    assert run_id == "run-123"
    assert fake.logged_artifacts == [str(artifact)]
    assert fake.tags == {"run_name": "generate"}


def test_mlflow_tracker_uses_direct_remote_api_with_cf_headers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, str, dict[str, str], dict[str, object]]] = []

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            import json

            return json.dumps(self._payload, ensure_ascii=True).encode("utf-8")

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

    def _fake_urlopen(req: request.Request, timeout: int = 60) -> _FakeResponse:
        import json

        body = req.data.decode("utf-8") if isinstance(req.data, bytes) else ""
        payload = json.loads(body) if body else {}
        headers = dict(req.header_items())
        method = req.get_method()
        calls.append((req.full_url, method, headers, payload))
        split = urlsplit(req.full_url)
        if split.path.endswith("/experiments/get-by-name"):
            assert method == "GET"
            assert parse_qs(split.query) == {"experiment_name": ["discoverex-core"]}
            return _FakeResponse({"experiment": {"experiment_id": "exp-123"}})
        if split.path.endswith("/runs/create"):
            assert method == "POST"
            return _FakeResponse({"run": {"info": {"run_id": "run-123"}}})
        if split.path.endswith("/runs/log-batch"):
            assert method == "POST"
            return _FakeResponse({})
        if split.path.endswith("/runs/update"):
            assert method == "POST"
            return _FakeResponse({})
        raise AssertionError(req.full_url)

    monkeypatch.setattr(request, "urlopen", _fake_urlopen)
    scene_json = tmp_path / "scene.json"
    scene_json.write_text("{}", encoding="utf-8")
    verification = tmp_path / "verification.json"
    verification.write_text("{}", encoding="utf-8")
    prompt_bundle = tmp_path / "prompt_bundle.json"
    prompt_bundle.write_text("{}", encoding="utf-8")
    execution_config = tmp_path / "resolved_execution_config.json"
    execution_config.write_text("{}", encoding="utf-8")
    tracker = MLflowTrackerAdapter(
        tracking_uri="https://mlflow.example.com",
        artifact_bucket="orchestrator-artifacts",
        cf_access_client_id="cf-id",
        cf_access_client_secret="cf-secret",
    )
    run_id = tracker.log_pipeline_run(
        run_name="generate",
        params={
            "scene_id": "scene-1",
            "version_id": "ver-1",
            "background_prompt_used": "forest",
            "prefect.flow_run_id": "prefect-flow-123",
            "prefect.flow_run_name": "verify-smoke-track-upload",
        },
        metrics={"pass": 1.0},
        artifacts=[scene_json, verification, prompt_bundle, execution_config],
    )

    assert run_id == "run-123"
    assert [urlsplit(url).path.rsplit("/", 1)[-1] for url, _, _, _ in calls] == [
        "get-by-name",
        "create",
        "log-batch",
        "update",
    ]
    assert calls[0][2]["Cf-access-client-id"] == "cf-id"
    assert calls[0][2]["Cf-access-client-secret"] == "cf-secret"
    assert calls[1][3]["tags"] == [
        {"key": "mlflow.runName", "value": "generate"},
        {"key": "prefect.flow_run_id", "value": "prefect-flow-123"},
        {"key": "prefect.flow_run_name", "value": "verify-smoke-track-upload"},
    ]
    assert calls[2][3]["run_id"] == "run-123"


def test_mlflow_tracker_creates_experiment_when_get_by_name_returns_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            import json

            return json.dumps(self._payload, ensure_ascii=True).encode("utf-8")

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

    def _fake_urlopen(req: request.Request, timeout: int = 60) -> _FakeResponse:
        _ = timeout
        split = urlsplit(req.full_url)
        calls.append((req.get_method(), split.path))
        if split.path.endswith("/experiments/get-by-name"):
            raise request.HTTPError(
                req.full_url,
                404,
                "Not Found",
                hdrs=None,
                fp=None,
            )
        if split.path.endswith("/experiments/create"):
            return _FakeResponse({"experiment_id": "exp-404-created"})
        if split.path.endswith("/runs/create"):
            return _FakeResponse({"run": {"info": {"run_id": "run-123"}}})
        if split.path.endswith("/runs/log-batch"):
            return _FakeResponse({})
        if split.path.endswith("/runs/update"):
            return _FakeResponse({})
        raise AssertionError(req.full_url)

    monkeypatch.setattr(request, "urlopen", _fake_urlopen)

    tracker = MLflowTrackerAdapter(tracking_uri="https://mlflow.example.com")

    run_id = tracker.log_pipeline_run(
        run_name="generate",
        params={"scene_id": "scene-1"},
        metrics={"pass": 1.0},
        artifacts=[],
    )

    assert run_id == "run-123"
    assert calls[:2] == [
        ("GET", "/api/2.0/mlflow/experiments/get-by-name"),
        ("POST", "/api/2.0/mlflow/experiments/create"),
    ]
