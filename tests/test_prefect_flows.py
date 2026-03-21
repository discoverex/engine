from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from prefect.runtime import flow_run

import infra.prefect.dispatch as prefect_dispatch
import infra.prefect.flow as prefect_entrypoint
from infra.prefect.artifacts import summarize_payload
from discoverex.application.flows.run_engine_job import run_engine_job
from discoverex.config_loader import load_pipeline_config
from discoverex.settings import build_settings
from infra.prefect.job_spec import (
    coerce_args,
    coerce_overrides,
    config_name,
    mapped_command,
)
from infra.prefect.runtime import build_runtime_env


class _FakeLogger:
    def __init__(self, sink: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._sink = sink

    def debug(self, message: str, *args: Any) -> None:
        self._sink.append((message, args))

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
            "entrypoint": ["prefect_flow.py:run_generate_job_flow"],
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
    assert isinstance(captured["resolved_settings"], dict)
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
    assert isinstance(captured["resolved_settings"], dict)
    assert payload["preparation"]["mode"] == "worker"
    assert payload["run_mode"] == "inline"


def test_run_engine_job_prefers_inline_resolved_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    resolved = load_pipeline_config(
        config_name="generate",
        config_dir=repo_root / "conf",
    ).model_dump(mode="python")

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
            "entrypoint": ["prefect_flow.py:run_generate_job_flow"],
            "inputs": {
                "contract_version": "v2",
                "command": "generate",
                "config_name": "ignored",
                "config_dir": "missing-conf-dir",
                "resolved_config": resolved,
                "args": {"background_asset_ref": "bg://dummy"},
            },
        },
        cwd=tmp_path,
    )

    assert captured["resolved_settings"] == build_settings(
        config_name="ignored",
        config_dir=str(Path(__file__).resolve().parents[1] / "missing-conf-dir"),
        overrides=[],
        resolved_config=resolved,
        env=dict(os.environ),
    ).model_dump(mode="python")
    assert payload["ok"] is True


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


def test_summarize_payload_includes_tracking_and_artifact_ids() -> None:
    summary = summarize_payload(
        {
            "status": "approved",
            "flow_run_id": "prefect-flow-123",
            "attempt": 1,
            "artifact_bucket": "orchestrator-artifacts",
            "artifact_prefix": "jobs/prefect-flow-123/attempt-1/",
            "mlflow_run_id": "mlflow-run-123",
            "effective_tracking_uri": "https://mlflow.example.com",
        }
    )

    assert summary["flow_run_id"] == "prefect-flow-123"
    assert summary["artifact_bucket"] == "orchestrator-artifacts"
    assert summary["artifact_prefix"] == "jobs/prefect-flow-123/attempt-1/"
    assert summary["mlflow_run_id"] == "mlflow-run-123"
    assert summary["effective_tracking_uri"] == "https://mlflow.example.com"


def test_dispatch_engine_job_calls_nested_generate_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sink: list[tuple[str, tuple[Any, ...]]] = []
    monkeypatch.setattr(prefect_dispatch, "get_run_logger", lambda: _FakeLogger(sink))

    captured: dict[str, Any] = {}

    def _fake_nested_flow(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"status": "completed", "scene_id": "scene-1"}

    monkeypatch.setattr(
        "discoverex.application.flows.engine_entry.load_pipeline_config",
        lambda **kwargs: "cfg",
    )
    monkeypatch.setattr(
        "discoverex.application.flows.engine_entry.normalize_pipeline_config_for_worker_runtime",
        lambda config: type(
            "Cfg",
            (),
            {"runtime": type("Runtime", (), {"artifacts_root": str(tmp_path)})()},
        )(),
    )
    monkeypatch.setattr(
        "discoverex.application.flows.engine_entry.build_execution_snapshot",
        lambda **kwargs: {
            "command": kwargs["command"],
            "config_name": kwargs["config_name"],
        },
    )
    monkeypatch.setattr(
        "discoverex.application.flows.engine_entry.write_execution_snapshot",
        lambda **kwargs: tmp_path / "resolved_execution_config.json",
    )
    monkeypatch.setattr(
        "discoverex.application.flows.engine_entry._resolve_subflow",
        lambda config, command: _fake_nested_flow,
    )

    result = prefect_dispatch.dispatch_engine_job(
        {
            "command": "generate",
            "config_name": "generate",
            "config_dir": "conf",
            "resolved_settings": build_settings(
                config_name="generate",
                config_dir="conf",
                overrides=["profile=generator_pixart_gpu_v2_hidden_object"],
                env={},
            ).model_dump(mode="python"),
            "args": {"background_prompt": "harbor"},
            "overrides": ["profile=generator_pixart_gpu_v2_hidden_object"],
        },
        cwd=tmp_path,
        env={},
    )

    assert captured["args"] == {"background_prompt": "harbor"}
    assert captured["execution_snapshot"]["command"] == "generate"
    assert str(captured["execution_snapshot_path"]).endswith(
        "resolved_execution_config.json"
    )
    assert result.payload["status"] == "completed"
    assert result.stdout == json.dumps(result.payload, ensure_ascii=True)
    assert result.stderr == ""
    assert sink[-1][0] == (
        "engine nested flow handoff: flow=%s command=%s config_name=%s override_count=%d"
    )
    assert sink[-1][1][0] == "_fake_nested_flow"


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


def test_build_runtime_env_merges_runtime_extra_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("BASE_ONLY", "1")
    monkeypatch.setenv("SHARED_KEY", "from-os")
    monkeypatch.setattr("infra.prefect.runtime.repo_root", lambda: tmp_path)

    env = build_runtime_env(
        job_spec={
            "engine": "discoverex",
            "run_mode": "repo",
            "job_name": "job-1",
            "env": {
                "RUNNER_ONLY": "runner",
                "SHARED_KEY": "from-job-spec-env",
            },
            "inputs": {
                "runtime": {
                    "extra_env": {
                        "EXTRA_ONLY": "extra",
                        "SHARED_KEY": "from-runtime-extra-env",
                        "MLFLOW_TRACKING_URI": "http://mlflow.example.com",
                        "UV_CACHE_DIR": "/cache/uv",
                    }
                }
            },
        },
        flow_run_id="flow-1",
        attempt=1,
        outputs_prefix="jobs/flow-1/attempt-1/",
        resume_key=None,
        checkpoint_dir=None,
    )

    assert env["BASE_ONLY"] == "1"
    assert env["RUNNER_ONLY"] == "runner"
    assert env["EXTRA_ONLY"] == "extra"
    assert env["SHARED_KEY"] == "from-runtime-extra-env"
    assert env["MLFLOW_TRACKING_URI"] == "http://mlflow.example.com"
    assert env["UV_CACHE_DIR"] == "/cache/uv"


def test_build_runtime_env_preserves_huggingface_auth_from_worker_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf-token")
    monkeypatch.setenv("HUGGINGFACE_HUB_TOKEN", "hub-token")
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "legacy-token")
    monkeypatch.setattr("infra.prefect.runtime.repo_root", lambda: tmp_path)

    env = build_runtime_env(
        job_spec={
            "engine": "discoverex",
            "run_mode": "inline",
            "job_name": "job-1",
            "env": {},
            "inputs": {"runtime": {"extra_env": {}}},
        },
        flow_run_id="flow-1",
        attempt=1,
        outputs_prefix="jobs/flow-1/attempt-1/",
        resume_key=None,
        checkpoint_dir=None,
    )

    assert env["HF_TOKEN"] == "hf-token"
    assert env["HUGGINGFACE_HUB_TOKEN"] == "hub-token"
    assert env["HUGGINGFACE_TOKEN"] == "legacy-token"


def test_repo_root_prefect_entrypoint_routes_job_into_engine_entry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Any] = {}
    logged: list[tuple[str, tuple[Any, ...]]] = []
    resolved = load_pipeline_config(
        config_name="gen_verify",
        config_dir="conf",
    ).model_dump(mode="python")

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
        prefect_entrypoint,
        "engine_job_task",
        lambda payload, cwd, env: prefect_dispatch.DispatchResult(
            payload=fake_run_engine_entry(
                **{
                    "command": mapped_command(str(payload.get("command", ""))),
                    "args": coerce_args(payload.get("args")),
                    "config_name": config_name(payload),
                    "config_dir": str(payload.get("config_dir") or "conf"),
                    "resolved_config": payload.get("resolved_config"),
                    "overrides": coerce_overrides(payload.get("overrides")),
                }
            ),
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
                    "resolved_config": resolved,
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
        "resolved_config": resolved,
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
    assert (
        logged[0][0]
        == "prefect runtime import path: flow_module=%s dispatch_module=%s dispatch_source=%s"
    )
    assert logged[1][0] == "engine flow start: %s"
    assert logged[-1][0] == "engine payload summary: %s"
    start_summary = json.loads(str(logged[1][1][0]))
    assert (
        start_summary["resolved_config"]["runtime"]["env"]["tracking_uri"]
        == "***REDACTED***"
    )
    assert "[discoverex-engine-flow] start" in capsys.readouterr().err


def test_repo_root_prefect_entrypoint_uploads_worker_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prefect_entrypoint,
        "engine_job_task",
        lambda payload, cwd, env: prefect_dispatch.DispatchResult(
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
                    "s3://bucket/jobs/flow-456/attempt-1/engine/scenes/s1/v1/metadata/scene.json"
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
    assert output["engine_artifact_uris"]["scene_json"].endswith(
        "/scenes/s1/v1/metadata/scene.json"
    )


def test_repo_root_prefect_entrypoint_raises_on_failed_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    uploaded: list[dict[str, Any]] = []
    monkeypatch.setattr(
        prefect_entrypoint,
        "engine_job_task",
        lambda payload, cwd, env: prefect_dispatch.DispatchResult(
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


def test_repo_root_prefect_entrypoint_runs_preflight_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        prefect_entrypoint,
        "validate_runtime_services",
        lambda **kwargs: calls.append("preflight"),
    )
    monkeypatch.setattr(
        prefect_entrypoint,
        "engine_job_task",
        lambda payload, cwd, env: prefect_dispatch.DispatchResult(
            payload={"status": "completed"},
            stdout='{"status":"completed"}\n',
            stderr="",
        ),
    )
    monkeypatch.setattr(prefect_entrypoint, "get_run_logger", lambda: _FakeLogger([]))

    output = prefect_entrypoint.run_job_flow.fn(
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

    assert output["status"] == "completed"
    assert calls == ["preflight"]


def test_repo_root_prefect_entrypoint_fails_when_preflight_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prefect_entrypoint,
        "validate_runtime_services",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("preflight failed")),
    )
    monkeypatch.setattr(prefect_entrypoint, "get_run_logger", lambda: _FakeLogger([]))

    with pytest.raises(RuntimeError, match="preflight failed"):
        prefect_entrypoint.run_job_flow.fn(
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


def _capture_uploaded(
    payload: dict[str, Any], uploaded: list[dict[str, Any]]
) -> dict[str, Any]:
    uploaded.append(payload)
    return {}
