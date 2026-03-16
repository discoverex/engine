from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from prefect.runtime import flow_run

import infra.prefect.dispatch as prefect_dispatch
import infra.prefect.flow as prefect_entrypoint
from discoverex.application.flows.run_engine_job import run_engine_job
from infra.prefect.job_spec import (
    coerce_args,
    coerce_overrides,
    config_name,
    mapped_command,
)


@pytest.fixture(autouse=True)
def mock_prefect_infra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Prefect infrastructure to prevent real API calls and Pydantic validation errors."""
    
    # 1. Mock the client context manager
    mock_client = MagicMock()
    mock_client.api_version.return_value = "3.0.0"
    
    class MockClientContext:
        def __init__(self) -> None:
            self.client = mock_client
        def __enter__(self) -> Any: return mock_client
        def __exit__(self, *args: Any) -> None: pass
        async def __aenter__(self) -> Any: return mock_client
        async def __aexit__(self, *args: Any) -> None: pass

    monkeypatch.setattr("prefect.client.orchestration.get_client", lambda **_: MockClientContext())
    
    # 2. CRITICAL: Mock the task itself to prevent TaskRunContext initialization
    # We make engine_job_task behave like a regular function instead of a Prefect task
    def mock_task_fn(payload: Any, cwd: Path, env: dict[str, str]) -> Any:
        return prefect_dispatch.dispatch_engine_job(payload, cwd=cwd, env=env)
    
    # Prefect tasks have a .fn attribute which is the original function
    monkeypatch.setattr(prefect_entrypoint.engine_job_task, "fn", mock_task_fn)
    # Also mock the task call itself if it's being called directly
    monkeypatch.setattr(prefect_entrypoint, "engine_job_task", mock_task_fn)


class _FakeLogger:
    def __init__(self, sink: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._sink = sink

    def info(self, message: str, *args: Any) -> None:
        self._sink.append((message, args))

    def error(self, message: str, *args: Any) -> None:
        self._sink.append((message, args))


def test_run_engine_job_executes_engine_entry_directly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.chdir(tmp_path)

    def fake_run_engine_entry(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True}

    run_engine_job_module = importlib.import_module(
        "discoverex.application.flows.run_engine_job"
    )
    monkeypatch.setattr(
        run_engine_job_module,
        "run_engine_entry",
        fake_run_engine_entry,
    )

    payload = run_engine_job(
        {
            "run_mode": "inline",
            "engine": "discoverex",
            "entrypoint": [
                "/bin/sh",
                "-lc",
                (
                    "PYTHONPATH=src python -m "
                    "discoverex.adapters.outbound.execution.launcher"
                ),
            ],
            "inputs": {
                "contract_version": "v2",
                "command": "generate",
                "args": {"background_asset_ref": "bg://dummy"},
            },
        },
        cwd=tmp_path,
    )

    assert captured["command"] == "generate"
    assert captured["config_name"] == "generate"
    assert payload["ok"] is True
    assert payload["preparation"]["mode"] == "worker"


def test_run_engine_job_accepts_bare_engine_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.chdir(tmp_path)

    def fake_run_engine_entry(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True}

    run_engine_job_module = importlib.import_module(
        "discoverex.application.flows.run_engine_job"
    )
    monkeypatch.setattr(
        run_engine_job_module,
        "run_engine_entry",
        fake_run_engine_entry,
    )

    payload = run_engine_job(
        json.dumps(
            {
                "contract_version": "v2",
                "command": "generate",
                "args": {"background_asset_ref": "bg://dummy"},
            },
            ensure_ascii=True,
        ),
        cwd=tmp_path,
    )

    assert captured["command"] == "generate"
    assert payload["preparation"]["mode"] == "worker"
    assert payload["run_mode"] == "inline"


def test_repo_root_prefect_entrypoint_exposes_run_job_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root))
    sys.modules.pop("prefect_flow", None)
    module = importlib.import_module("prefect_flow")
    assert module.run_job_flow.name == "discoverex-engine-flow"
    assert module.run_job_flow is prefect_entrypoint.run_job_flow
    assert module.run_generate_job_flow.name == "discoverex-generate-flow"
    assert module.run_generate_job_flow is prefect_entrypoint.run_generate_job_flow
    assert module.run_combined_job_flow.name == "discoverex-combined-flow"
    assert module.run_combined_job_flow is prefect_entrypoint.run_combined_job_flow


def test_flow_kind_entrypoint_rejects_mismatched_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prefect_entrypoint, "get_run_logger", lambda: _FakeLogger([]))
    monkeypatch.setattr(flow_run, "get_id", lambda: "flow-999")

    with pytest.raises(RuntimeError, match="flow_kind=verify"):
        prefect_entrypoint.run_verify_job_flow.fn(
            json.dumps(
                {
                    "run_mode": "inline",
                    "engine": "discoverex",
                    "inputs": {
                        "contract_version": "v2",
                        "command": "generate",
                        "args": {"background_prompt": "test"},
                    },
                },
                ensure_ascii=True,
            )
        )


def test_repo_root_prefect_entrypoint_routes_job_into_engine_entry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Any] = {}
    logged: list[tuple[str, tuple[Any, ...]]] = []

    def fake_run_engine_entry(**kwargs: Any) -> dict[str, Any]:
        captured["kwargs"] = kwargs
        captured["env"] = {
            "ORCH_FLOW_RUN_ID": os.environ.get("ORCH_FLOW_RUN_ID"),
            "ORCH_ATTEMPT": os.environ.get("ORCH_ATTEMPT"),
            "ORCH_OUTPUTS_PREFIX": os.environ.get("ORCH_OUTPUTS_PREFIX"),
            "ORCH_ENGINE_ARTIFACT_DIR": os.environ.get("ORCH_ENGINE_ARTIFACT_DIR"),
            "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH": os.environ.get(
                "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"
            ),
        }
        return {"status": "completed", "scene_id": "scene-1", "version_id": "v1"}

    monkeypatch.setattr(
        prefect_dispatch,
        "dispatch_engine_job",
        lambda payload, *, cwd, env: prefect_dispatch.DispatchResult(
            payload=fake_run_engine_entry(**{
                "command": mapped_command(str(payload.get("command", ""))),
                "args": coerce_args(payload.get("args")),
                "config_name": config_name(payload),
                "config_dir": str(payload.get("config_dir") or "conf"),
                "overrides": coerce_overrides(payload.get("overrides")),
            }),
            stdout='{"status":"completed"}\n',
            stderr="",
        ),
    )
    monkeypatch.setattr(
        prefect_entrypoint, "get_run_logger", lambda: _FakeLogger(logged)
    )
    monkeypatch.setattr(flow_run, "get_id", lambda: "flow-123")

    output = prefect_entrypoint.run_job_flow.fn(
        json.dumps(
            {
                "run_mode": "inline",
                "engine": "discoverex",
                "job_name": "prefect-smoke",
                "inputs": {
                    "contract_version": "v1",
                    "command": "gen-verify",
                    "args": {"background_asset_ref": "bg://dummy"},
                },
                "env": {"X_TEST_ENV": "1"},
            },
            ensure_ascii=True,
        )
    )

    assert captured["kwargs"] == {
        "command": "generate",
        "args": {"background_asset_ref": "bg://dummy"},
        "config_name": "gen_verify",
        "config_dir": "conf",
        "overrides": [],
    }
    assert captured["env"]["ORCH_FLOW_RUN_ID"] == "flow-123"
    assert captured["env"]["ORCH_ATTEMPT"] == "1"
    assert captured["env"]["ORCH_OUTPUTS_PREFIX"] == "jobs/flow-123/attempt-1/"
    assert captured["env"]["ORCH_ENGINE_ARTIFACT_DIR"]
    assert captured["env"]["ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"]
    assert output["job_name"] == "prefect-smoke"
    assert output["engine"] == "discoverex"
    assert output["run_mode"] == "inline"
    assert output["flow_run_id"] == "flow-123"
    assert output["attempt"] == 1
    assert output["outputs_prefix"] == "jobs/flow-123/attempt-1/"
    assert logged[0][0] == "engine flow start: %s"
    assert logged[-1][0] == "engine payload summary: %s"
    assert "[discoverex-engine-flow] start" in capsys.readouterr().err


def test_repo_root_prefect_entrypoint_uploads_worker_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prefect_dispatch,
        "dispatch_engine_job",
        lambda payload, *, cwd, env: prefect_dispatch.DispatchResult(
            payload={
                "status": "completed",
                "scene_id": "s1",
                "version_id": "v1",
            },
            stdout='{"status":"completed","scene_id":"s1","version_id":"v1"}\n',
            stderr="",
        ),
    )
    monkeypatch.setattr(prefect_entrypoint, "get_run_logger", lambda: _FakeLogger([]))
    monkeypatch.setattr(flow_run, "get_id", lambda: "flow-456")
    monkeypatch.setattr(
        prefect_entrypoint,
        "upload_worker_artifacts",
        lambda **kwargs: {
            "stdout_uri": "s3://bucket/jobs/flow-456/attempt-1/stdout.log",
            "stderr_uri": "s3://bucket/jobs/flow-456/attempt-1/stderr.log",
            "result_uri": "s3://bucket/jobs/flow-456/attempt-1/result.json",
            "manifest_uri": "s3://bucket/jobs/flow-456/attempt-1/artifacts.json",
            "engine_manifest_uri": (
                "s3://bucket/jobs/flow-456/attempt-1/engine-artifacts.json"
            ),
            "engine_artifact_uris": {
                "scene_json": (
                    "s3://bucket/jobs/flow-456/attempt-1/engine/scene/scene.json"
                )
            },
        },
    )

    output = prefect_entrypoint.run_job_flow.fn(
        json.dumps(
            {
                "run_mode": "repo",
                "engine": "discoverex",
                "job_name": "prefect-upload",
                "entrypoint": ["python", "-m", "x"],
                "inputs": {
                    "contract_version": "v2",
                    "command": "generate",
                    "args": {"background_prompt": "test"},
                },
            },
            ensure_ascii=True,
        )
    )

    assert output["stdout_uri"].endswith("/stdout.log")
    assert output["manifest_uri"].endswith("/artifacts.json")
    assert output["engine_manifest_uri"].endswith("/engine-artifacts.json")
    assert output["engine_artifact_uris"]["scene_json"].endswith("/scene/scene.json")


def test_repo_root_prefect_entrypoint_raises_on_failed_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    uploaded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        prefect_dispatch,
        "dispatch_engine_job",
        lambda payload, *, cwd, env: prefect_dispatch.DispatchResult(
            payload={
                "status": "failed",
                "failure_reason": "boom",
                "scene_json": "",
            },
            stdout='{"status":"failed","failure_reason":"boom","scene_json":""}\n',
            stderr="stderr boom\n",
        ),
    )
    monkeypatch.setattr(prefect_entrypoint, "get_run_logger", lambda: _FakeLogger([]))
    monkeypatch.setattr(
        prefect_entrypoint,
        "upload_worker_artifacts",
        lambda **kwargs: _capture_uploaded(kwargs, uploaded),
    )

    with pytest.raises(RuntimeError) as exc_info:
        prefect_entrypoint.run_job_flow.fn(
            json.dumps(
                {
                    "run_mode": "inline",
                    "engine": "discoverex",
                    "job_name": "prefect-smoke",
                    "inputs": {
                        "contract_version": "v2",
                        "command": "generate",
                        "args": {"background_asset_ref": "bg://dummy"},
                    },
                },
                ensure_ascii=True,
            )
        )

    assert "engine flow returned failed payload" in str(exc_info.value)
    assert "boom" in str(exc_info.value)
    assert uploaded
    stderr_text = capsys.readouterr().err
    assert "[discoverex-engine-flow] failure-context" in stderr_text


def _capture_uploaded(
    payload: dict[str, Any], uploaded: list[dict[str, Any]]
) -> dict[str, Any]:
    uploaded.append(payload)
    return {}
