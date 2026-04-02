from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest

from discoverex.config_loader import load_pipeline_config
from infra.ops import register_orchestrator_job as _register_job
from infra.ops.job_types import JobSpec

register_job = cast(Any, _register_job)


def test_submit_job_spec_resolves_deployment_from_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeClient:
        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

        def read_deployments(self, *, deployment_filter, limit):  # type: ignore[no-untyped-def]
            captured["deployment_filter"] = deployment_filter
            captured["limit"] = limit
            return [
                SimpleNamespace(
                    id="12345678-1234-5678-1234-567812345678",
                    name="discoverex-generate-standard",
                )
            ]

        def create_flow_run_from_deployment(self, deployment_id, *, parameters, name, work_queue_name=None):  # type: ignore[no-untyped-def]
            captured["deployment_id"] = deployment_id
            captured["parameters"] = parameters
            captured["name"] = name
            captured["work_queue_name"] = work_queue_name
            return SimpleNamespace(id="flow-456", name="run-789")

    @contextmanager
    def _fake_temporary_settings(*, updates):  # type: ignore[no-untyped-def]
        captured["settings_updates"] = updates
        yield None

    def _fake_get_client(*, sync_client, httpx_settings):  # type: ignore[no-untyped-def]
        captured["sync_client"] = sync_client
        captured["httpx_settings"] = httpx_settings
        return _FakeClient()

    monkeypatch.setattr(register_job, "temporary_settings", _fake_temporary_settings)
    monkeypatch.setattr(register_job, "get_client", _fake_get_client)
    monkeypatch.setattr(register_job.SETTINGS, "prefect_cf_access_client_id", "cf-id")
    monkeypatch.setattr(
        register_job.SETTINGS,
        "prefect_cf_access_client_secret",
        "cf-secret",
    )

    output = register_job.submit_job_spec(
        job_spec={
            "run_mode": "inline",
            "engine": "discoverex",
            "entrypoint": ["prefect_flow.py:run_generate_job_flow"],
            "inputs": {
                "contract_version": "v2",
                "command": "generate",
                "config_name": "generate",
                "args": {"background_asset_ref": "bg://dummy"},
                "overrides": [],
                "runtime": {"extras": ["tracking"]},
            },
            "env": {},
            "outputs_prefix": None,
            "job_name": "generate--generate--none",
        },
        prefect_api_url="http://127.0.0.1:4200/api",
    )

    assert output["deployment"] == "discoverex-generate-standard"
    assert output["deployment_id"] == "12345678-1234-5678-1234-567812345678"
    assert output["flow_run_id"] == "flow-456"
    assert output["flow_run_name"] == "run-789"
    assert output["work_queue_name"] is None
    assert captured["sync_client"] is True
    assert captured["settings_updates"] == {
        register_job.PREFECT_API_URL: "http://127.0.0.1:4200/api"
    }
    assert captured["httpx_settings"] == {
        "headers": {
            "User-Agent": "discoverex-job-register/1.0",
            "CF-Access-Client-Id": "cf-id",
            "CF-Access-Client-Secret": "cf-secret",
        }
    }
    parameters = cast(dict[str, object], captured["parameters"])
    submitted = json.loads(str(parameters["job_spec_json"]))
    assert "resolved_config" in submitted["inputs"]
    assert submitted["inputs"]["resolved_config"]["runtime"]["width"] == 1024


def test_submit_job_spec_falls_back_to_worker_cf_tokens_for_prefect_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(register_job.SETTINGS, "prefect_cf_access_client_id", "")
    monkeypatch.setattr(register_job.SETTINGS, "prefect_cf_access_client_secret", "")
    monkeypatch.setattr(register_job.SETTINGS, "cf_access_client_id", "worker-id")
    monkeypatch.setattr(
        register_job.SETTINGS,
        "cf_access_client_secret",
        "worker-secret",
    )

    assert register_job._client_httpx_settings() == {
        "headers": {
            "User-Agent": "discoverex-job-register/1.0",
            "CF-Access-Client-Id": "worker-id",
            "CF-Access-Client-Secret": "worker-secret",
        }
    }


def test_submit_job_spec_preserves_explicit_resolved_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    explicit = load_pipeline_config(
        config_name="generate", config_dir="conf"
    ).model_dump(mode="python")
    explicit["runtime"]["width"] = 2048

    class _FakeClient:
        def __enter__(self) -> "_FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

        def read_deployments(self, *, deployment_filter, limit):  # type: ignore[no-untyped-def]
            _ = (deployment_filter, limit)
            return [
                SimpleNamespace(
                    id="12345678-1234-5678-1234-567812345678",
                    name="discoverex-generate-standard",
                )
            ]

        def create_flow_run_from_deployment(self, deployment_id, *, parameters, name, work_queue_name=None):  # type: ignore[no-untyped-def]
            _ = (deployment_id, name, work_queue_name)
            captured["parameters"] = parameters
            return SimpleNamespace(id="flow-456", name="run-789")

    @contextmanager
    def _fake_temporary_settings(*, updates):  # type: ignore[no-untyped-def]
        _ = updates
        yield None

    def _fake_get_client(*, sync_client, httpx_settings):  # type: ignore[no-untyped-def]
        _ = (sync_client, httpx_settings)
        return _FakeClient()

    monkeypatch.setattr(register_job, "temporary_settings", _fake_temporary_settings)
    monkeypatch.setattr(register_job, "get_client", _fake_get_client)

    register_job.submit_job_spec(
        job_spec=cast(
            JobSpec,
            {
            "run_mode": "inline",
            "engine": "discoverex",
            "entrypoint": ["prefect_flow.py:run_generate_job_flow"],
            "inputs": {
                "contract_version": "v2",
                "command": "generate",
                "config_name": "generate",
                "config_dir": "conf",
                "resolved_config": explicit,
                "args": {"background_asset_ref": "bg://dummy"},
                "overrides": [],
                "runtime": {"extras": ["tracking"]},
            },
            "env": {},
            "outputs_prefix": None,
            },
        ),
        prefect_api_url="http://127.0.0.1:4200/api",
    )

    parameters = cast(dict[str, object], captured["parameters"])
    submitted = json.loads(str(parameters["job_spec_json"]))
    assert submitted["inputs"]["resolved_config"]["runtime"]["width"] == 2048
