from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "infra" / "register"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

deploy_flows = importlib.import_module("deploy_prefect_flows")


def test_resolved_entrypoint_defaults_by_flow_kind() -> None:
    assert (
        deploy_flows._resolved_entrypoint("generate", None)
        == "prefect_flow.py:run_generate_job_flow"
    )
    assert (
        deploy_flows._resolved_entrypoint("combined", None)
        == "prefect_flow.py:run_combined_job_flow"
    )


def test_flow_source_uses_commit_sha_for_full_hash() -> None:
    source = deploy_flows._flow_source(
        "https://github.com/example/engine.git",
        "1234567890abcdef1234567890abcdef12345678",
    )

    assert source._url == "https://github.com/example/engine.git"
    assert source._commit_sha == "1234567890abcdef1234567890abcdef12345678"
    assert source._branch is None


def test_flow_source_uses_branch_for_non_commit_ref() -> None:
    source = deploy_flows._flow_source(
        "https://github.com/example/engine.git",
        "feat/remote-source",
    )

    assert source._url == "https://github.com/example/engine.git"
    assert source._branch == "feat/remote-source"
    assert source._commit_sha is None


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


def test_deploy_remote_flow_uses_from_source_and_deploy(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class _FakeRemoteFlow:
        def deploy(self, **kwargs: Any) -> str:
            captured["deploy_kwargs"] = kwargs
            return "deployment-123"

    def _fake_from_source(*, source: Any, entrypoint: str) -> _FakeRemoteFlow:
        captured["source"] = source
        captured["entrypoint"] = entrypoint
        return _FakeRemoteFlow()

    monkeypatch.setattr(deploy_flows.flow, "from_source", _fake_from_source)

    deployment_id = deploy_flows._deploy_remote_flow(
        engine="discoverex",
        flow_kind="generate",
        branch="feat/remote-source",
        repo_url="https://github.com/example/engine.git",
        ref="feat/remote-source",
        flow_entrypoint="prefect_flow.py:run_generate_job_flow",
        work_pool_name="gpu-pool",
        work_queue_name="gpu-fixed",
        deployment_version="20260312120000",
        deployment_name="discoverex-naturalness-experiment-feat-remote-source",
        deployment_suffix="naturalness",
    )

    assert deployment_id == "deployment-123"
    assert captured["entrypoint"] == "prefect_flow.py:run_generate_job_flow"
    assert captured["source"]._url == "https://github.com/example/engine.git"
    assert captured["source"]._branch == "feat/remote-source"
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
        "work_pool_name": "local-process",
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
        "_deploy_remote_flow",
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
        "repo_url": "https://github.com/example/engine.git",
        "ref": "main",
        "flow_entrypoint": "prefect_flow.py:run_generate_job_flow",
        "work_pool_name": "local-process",
        "work_queue_name": "gpu-fixed",
        "deployment_version": out["deployment_version"],
        "deployment_name": "discoverex-naturalness-experiment-feat-remote-source",
        "deployment_suffix": "",
    }
    assert out["deployment_name"] == "discoverex-naturalness-experiment-feat-remote-source"


def test_build_parser_marks_script_as_remote_source_registrar() -> None:
    parser = deploy_flows._build_parser()
    assert "remote-source Prefect deployment" in parser.description
    parsed = parser.parse_args(["--branch", "dev"])
    assert parsed.branch == "dev"
    assert parsed.flow_kind == "combined"
    assert parsed.flow_entrypoint is None
    assert parsed.repo_url == "https://github.com/discoverex/engine.git"
    assert parsed.ref is None
    assert parsed.deployment_version
    assert parsed.deployment_suffix == ""
