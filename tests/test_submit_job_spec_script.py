from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "infra" / "register"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
register_job = importlib.import_module("register_orchestrator_job")


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
                    name="discoverex-engine-job",
                )
            ]

        def create_flow_run_from_deployment(self, deployment_id, *, parameters, name):  # type: ignore[no-untyped-def]
            captured["deployment_id"] = deployment_id
            captured["parameters"] = parameters
            captured["name"] = name
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
            "entrypoint": [
                "/bin/sh",
                "-lc",
                "python -m discoverex.adapters.outbound.execution.launcher",
            ],
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

    assert output["deployment"] == "discoverex-engine-job"
    assert output["deployment_id"] == "12345678-1234-5678-1234-567812345678"
    assert output["flow_run_id"] == "flow-456"
    assert output["flow_run_name"] == "run-789"
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
