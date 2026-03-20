from __future__ import annotations

import json
import os
import sys
from typing import Any, cast

from infra.register import deploy_prefect_flows as _deploy_flows

deploy_flows = cast(Any, _deploy_flows)


def test_resolved_entrypoint_defaults_by_flow_kind() -> None:
    assert (
        deploy_flows._resolved_entrypoint("generate", None)
        == "prefect_flow.py:run_generate_job_flow"
    )
    assert (
        deploy_flows._resolved_entrypoint("combined", None)
        == "prefect_flow.py:run_combined_job_flow"
    )


def test_load_flow_imports_entrypoint_object(monkeypatch: Any) -> None:
    class _Module:
        run_generate_job_flow = object()

    captured: dict[str, Any] = {}

    def _fake_import_module(name: str) -> _Module:
        captured["module_name"] = name
        return _Module()

    monkeypatch.setattr(deploy_flows.importlib, "import_module", _fake_import_module)

    loaded = deploy_flows._load_flow("prefect_flow.py:run_generate_job_flow")

    assert captured["module_name"] == "prefect_flow"
    assert loaded is _Module.run_generate_job_flow


def test_prefect_settings_sets_headers_temporarily(monkeypatch: Any) -> None:
    monkeypatch.setattr(deploy_flows, "_extra_headers", lambda: {"X-Test": "1"})
    captured: dict[str, object] = {}

    class _FakeTemporarySettings:
        def __init__(self, *, updates: dict[object, object]) -> None:
            captured["updates"] = updates

        def __enter__(self) -> None:
            return None

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

    monkeypatch.setattr(
        deploy_flows,
        "temporary_settings",
        lambda *, updates: _FakeTemporarySettings(updates=updates),
    )
    previous = os.environ.get("PREFECT_CLIENT_CUSTOM_HEADERS")

    with deploy_flows._prefect_settings("https://prefect.example/api"):
        assert json.loads(os.environ["PREFECT_CLIENT_CUSTOM_HEADERS"]) == {
            "X-Test": "1"
        }

    assert captured["updates"] == {
        deploy_flows.PREFECT_API_URL: "https://prefect.example/api"
    }
    if previous is None:
        assert "PREFECT_CLIENT_CUSTOM_HEADERS" not in os.environ
    else:
        assert os.environ["PREFECT_CLIENT_CUSTOM_HEADERS"] == previous


def test_deploy_embedded_flow_uses_local_flow_and_deploy(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class _FakeFlow:
        def deploy(self, **kwargs: Any) -> str:
            captured["deploy_kwargs"] = kwargs
            return "deployment-123"

    fake_flow = _FakeFlow()

    def _fake_load_flow(entrypoint: str) -> _FakeFlow:
        captured["entrypoint"] = entrypoint
        return fake_flow

    monkeypatch.setattr(deploy_flows, "_load_flow", _fake_load_flow)

    deployment_id = deploy_flows._deploy_embedded_flow(
        engine="discoverex",
        flow_kind="generate",
        branch="feat/remote-source",
        flow_entrypoint="prefect_flow.py:run_generate_job_flow",
        work_pool_name="gpu-pool",
        work_queue_name="gpu-fixed",
        deployment_version="20260312120000",
        deployment_name="discoverex-naturalness-experiment-feat-remote-source",
        deployment_suffix="naturalness",
    )

    assert deployment_id == "deployment-123"
    assert captured["entrypoint"] == "prefect_flow.py:run_generate_job_flow"
    assert captured["deploy_kwargs"] == {
        "name": "discoverex-naturalness-experiment-feat-remote-source",
        "work_pool_name": "gpu-pool",
        "work_queue_name": "gpu-fixed",
        "job_variables": {},
        "build": False,
        "push": False,
        "description": "Execute the generate flow for branch 'feat/remote-source'.",
        "tags": ["discoverex", "generate", "feat/remote-source"],
        "version": "20260312120000",
        "print_next_steps": False,
    }


def test_main_dry_run_prints_remote_deployment_metadata(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_prefect_flows.py",
            "--branch",
            "dev",
            "--flow-kind",
            "verify",
            "--prefect-api-url",
            "https://prefect.example/api",
            "--dry-run",
        ],
    )

    code = deploy_flows.main()
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out == {
        "deployment_name": "discoverex-verify-dev",
        "engine": "discoverex",
        "flow_kind": "verify",
        "branch": "dev",
        "repo_url": "https://github.com/discoverex/engine.git",
        "ref": "dev",
        "entrypoint": "prefect_flow.py:run_verify_job_flow",
        "work_pool_name": "discoverex-fixed",
        "work_queue_name": "gpu-fixed",
        "deployment_version": out["deployment_version"],
        "deployment_suffix": "",
    }


def test_main_deploys_remote_flow(monkeypatch: Any, capsys: Any) -> None:
    captured: dict[str, Any] = {}

    class _FakeContext:
        def __enter__(self) -> None:
            captured["entered"] = True
            return None

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

    monkeypatch.setattr(deploy_flows, "_prefect_settings", lambda _url: _FakeContext())

    def _fake_deploy(**kwargs: Any) -> str:
        captured["deploy_kwargs"] = kwargs
        return "deployment-456"

    monkeypatch.setattr(
        deploy_flows,
        "_deploy_embedded_flow",
        _fake_deploy,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "deploy_prefect_flows.py",
            "--branch",
            "feat/remote-source",
            "--flow-kind",
            "generate",
            "--prefect-api-url",
            "https://prefect.example/api",
            "--repo-url",
            "https://github.com/example/engine.git",
            "--ref",
            "main",
            "--deployment-name",
            "discoverex-naturalness-experiment-feat-remote-source",
        ],
    )

    code = deploy_flows.main()
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert captured["entered"] is True
    assert captured["deploy_kwargs"] == {
        "engine": "discoverex",
        "flow_kind": "generate",
        "branch": "feat/remote-source",
        "flow_entrypoint": "prefect_flow.py:run_generate_job_flow",
        "work_pool_name": "discoverex-fixed",
        "work_queue_name": "gpu-fixed",
        "deployment_version": out["deployment_version"],
        "deployment_name": "discoverex-naturalness-experiment-feat-remote-source",
        "deployment_suffix": "",
    }
    assert (
        out["deployment_name"] == "discoverex-naturalness-experiment-feat-remote-source"
    )


def test_build_parser_marks_script_as_remote_source_registrar() -> None:
    parser = deploy_flows._build_parser()
    assert parser.description is not None
    assert "embedded-source Prefect deployment" in parser.description
    parsed = parser.parse_args(["--branch", "dev"])
    assert parsed.branch == "dev"
    assert parsed.flow_kind == "combined"
    assert parsed.flow_entrypoint is None
    assert parsed.repo_url == "https://github.com/discoverex/engine.git"
    assert parsed.ref is None
    assert parsed.deployment_version
    assert parsed.deployment_suffix == ""
