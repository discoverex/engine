from __future__ import annotations

import json
from urllib import request

import pytest

from infra.prefect.preflight import validate_runtime_services


class _FakeResponse:
    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        _ = (exc_type, exc, tb)


def _payload() -> dict[str, object]:
    return {
        "command": "generate",
        "config_name": "generate",
        "config_dir": "conf",
        "overrides": [],
        "resolved_settings": {
            "pipeline": {
                "models": {
                    "background_generator": {"_target_": "x"},
                    "background_upscaler": {"_target_": "x"},
                    "object_generator": {"_target_": "x"},
                    "hidden_region": {"_target_": "x"},
                    "inpaint": {"_target_": "x"},
                    "perception": {"_target_": "x"},
                    "fx": {"_target_": "x"},
                },
                "adapters": {
                    "artifact_store": {"_target_": "x"},
                    "metadata_store": {"_target_": "x"},
                    "tracker": {"_target_": "x"},
                    "scene_io": {"_target_": "x"},
                    "report_writer": {"_target_": "x"},
                },
                "runtime": {
                    "width": 512,
                    "height": 512,
                    "background_upscale_factor": 1,
                    "config_version": "config-v1",
                    "artifacts_root": "artifacts",
                    "model_runtime": {"device": "cuda"},
                    "env": {
                        "tracking_uri": "https://mlflow.example.com",
                        "artifact_bucket": "bucket",
                        "s3_endpoint_url": "",
                        "aws_access_key_id": "",
                        "aws_secret_access_key": "",
                        "metadata_db_url": "",
                    },
                },
                "thresholds": {
                    "logical_pass": 0.7,
                    "perception_pass": 0.7,
                    "final_pass": 0.75,
                },
                "model_versions": {
                    "background_generator": "v0",
                    "background_upscaler": "v0",
                    "object_generator": "v0",
                    "hidden_region": "v0",
                    "inpaint": "v0",
                    "perception": "v0",
                    "fx": "v0",
                },
            },
            "tracking": {"uri": "https://mlflow.example.com"},
            "storage": {
                "artifact_bucket": "bucket",
                "s3_endpoint_url": "",
                "aws_access_key_id": "",
                "aws_secret_access_key": "",
                "metadata_db_url": "",
                "storage_api_url": "https://storage.example",
            },
            "worker_http": {
                "cf_access_client_id": "cf-id",
                "cf_access_client_secret": "cf-secret",
                "prefect_api_url": "",
            },
            "runtime_paths": {
                "cache_dir": "",
                "uv_cache_dir": "",
                "model_cache_dir": "",
                "hf_home": "",
            },
            "execution": {
                "config_name": "generate",
                "config_dir": "conf",
                "overrides": [],
                "source": "hydra+env",
                "selected_profile": "",
                "flow_run_id": "flow-123",
                "flow_run_name": "",
                "deployment_name": "",
            },
        },
    }


def test_validate_runtime_services_checks_mlflow_and_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake_urlopen(req: request.Request, timeout: int = 20) -> _FakeResponse:
        calls.append(req.full_url)
        if req.full_url.endswith("/health"):
            return _FakeResponse("{}")
        return _FakeResponse(json.dumps([{"kind": "stdout", "url": "u", "object_uri": "o"}]))

    monkeypatch.setattr(request, "urlopen", _fake_urlopen)

    validate_runtime_services(payload=_payload(), env={}, logger=_Logger())

    assert calls == [
        "https://mlflow.example.com/health",
        "https://storage.example/artifact/v1/presign/batch",
    ]


def test_validate_runtime_services_fails_on_empty_storage_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(req: request.Request, timeout: int = 20) -> _FakeResponse:
        if req.full_url.endswith("/health"):
            return _FakeResponse("{}")
        return _FakeResponse("")

    monkeypatch.setattr(request, "urlopen", _fake_urlopen)

    with pytest.raises(RuntimeError, match="storage preflight failed"):
        validate_runtime_services(payload=_payload(), env={}, logger=_Logger())


class _Logger:
    def info(self, message: str, *args: object) -> None:
        _ = (message, args)
