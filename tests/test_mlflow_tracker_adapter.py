from __future__ import annotations

import sys
import types
from pathlib import Path

from discoverex.adapters.outbound.tracking.mlflow import MLflowTrackerAdapter


class _FakeRun:
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


class _FakeHeaderRegistry:
    def __init__(self) -> None:
        self._request_header_provider_registry: list[object] = []

    def register(self, provider_cls) -> None:  # type: ignore[no-untyped-def]
        self._request_header_provider_registry.append(provider_cls())

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._request_header_provider_registry)


def test_mlflow_tracker_logs_artifacts_for_local_tracking(
    monkeypatch, tmp_path: Path
) -> None:
    fake = _FakeMLflow()
    monkeypatch.setitem(sys.modules, "mlflow", fake)

    artifact = tmp_path / "scene.json"
    artifact.write_text("{}", encoding="utf-8")
    tracker = MLflowTrackerAdapter(tracking_uri="sqlite:///mlflow.db")
    tracker.log_pipeline_run(
        run_name="generate",
        params={"scene_id": "scene-1", "version_id": "ver-1"},
        metrics={"pass": 1.0},
        artifacts=[artifact],
    )

    assert fake.logged_artifacts == [str(artifact)]
    assert fake.tags == {"run_name": "generate"}


def test_mlflow_tracker_uses_tags_for_remote_tracking(
    monkeypatch, tmp_path: Path
) -> None:
    fake = _FakeMLflow()
    monkeypatch.setitem(sys.modules, "mlflow", fake)
    fake_registry = _FakeHeaderRegistry()
    tracking_pkg = types.ModuleType("mlflow.tracking")
    request_header_pkg = types.ModuleType("mlflow.tracking.request_header")
    registry_module = types.ModuleType("mlflow.tracking.request_header.registry")
    registry_module._request_header_provider_registry = (  # type: ignore[attr-defined]
        fake_registry
    )
    registry_module.register = fake_registry.register  # type: ignore[attr-defined]
    tracking_pkg.request_header = request_header_pkg  # type: ignore[attr-defined]
    request_header_pkg.registry = registry_module  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlflow.tracking", tracking_pkg)
    monkeypatch.setitem(sys.modules, "mlflow.tracking.request_header", request_header_pkg)
    monkeypatch.setitem(
        sys.modules,
        "mlflow.tracking.request_header.registry",
        registry_module,
    )
    monkeypatch.setenv("CF_ACCESS_CLIENT_ID", "cf-client-id")
    monkeypatch.setenv("CF_ACCESS_CLIENT_SECRET", "cf-client-secret")

    scene_json = tmp_path / "scene.json"
    scene_json.write_text("{}", encoding="utf-8")
    verification = tmp_path / "verification.json"
    verification.write_text("{}", encoding="utf-8")
    prompt_bundle = tmp_path / "prompt_bundle.json"
    prompt_bundle.write_text("{}", encoding="utf-8")
    tracker = MLflowTrackerAdapter(
        tracking_uri="https://mlflow.example.com",
        artifact_bucket="orchestrator-artifacts",
    )
    tracker.log_pipeline_run(
        run_name="generate",
        params={
            "scene_id": "scene-1",
            "version_id": "ver-1",
            "background_prompt_used": "forest",
        },
        metrics={"pass": 1.0},
        artifacts=[scene_json, verification, prompt_bundle],
    )

    assert fake.logged_artifacts == []
    assert fake.tags["artifact_logging_mode"] == "metadata_only"
    assert (
        fake.tags["artifact_scene_json_uri"]
        == "s3://orchestrator-artifacts/scenes/scene-1/ver-1/scene.json"
    )
    assert (
        fake.tags["artifact_verification_uri"]
        == "s3://orchestrator-artifacts/scenes/scene-1/ver-1/verification.json"
    )
    assert (
        fake.tags["artifact_prompt_bundle_uri"]
        == "s3://orchestrator-artifacts/scenes/scene-1/ver-1/prompt_bundle.json"
    )
    providers = fake_registry._request_header_provider_registry
    assert len(providers) == 1
    assert providers[0].request_headers() == {
        "CF-Access-Client-Id": "cf-client-id",
        "CF-Access-Client-Secret": "cf-client-secret",
    }
