from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

import prefect_flow
from discoverex.application.flows.run_engine_job import run_engine_job


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

    run_engine_job_module = importlib.import_module("discoverex.application.flows.run_engine_job")
    monkeypatch.setattr(run_engine_job_module, "run_engine_entry", fake_run_engine_entry)

    payload = run_engine_job(
        {
            "run_mode": "inline",
            "engine": "discoverex",
            "entrypoint": [
                "/bin/sh",
                "-lc",
                "PYTHONPATH=src python -m discoverex.adapters.outbound.execution.launcher",
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

    run_engine_job_module = importlib.import_module("discoverex.application.flows.run_engine_job")
    monkeypatch.setattr(run_engine_job_module, "run_engine_entry", fake_run_engine_entry)

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


def test_repo_root_prefect_entrypoint_exposes_run_job_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root))
    sys.modules.pop("prefect_flow", None)
    module = importlib.import_module("prefect_flow")
    assert module.run_job_flow.name == "disoverex-engine-flow"


def test_repo_root_prefect_entrypoint_runs_launcher_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Any] = {}
    logged: list[tuple[str, tuple[Any, ...]]] = []

    def fake_run_launcher_process(
        *,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str],
        logger: Any,
    ) -> prefect_flow.LauncherExecution:
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        captured["logger"] = logger
        return prefect_flow.LauncherExecution(
            returncode=0,
            stdout='{"status":"ok"}\n',
            stderr="",
        )

    monkeypatch.setattr(prefect_flow, "_run_launcher_process", fake_run_launcher_process)
    monkeypatch.setattr(prefect_flow, "get_run_logger", lambda: _FakeLogger(logged))
    monkeypatch.setattr(prefect_flow.flow_run, "get_id", lambda: "flow-123")

    output = prefect_flow.run_job_flow.fn(
        json.dumps(
            {
                "run_mode": "inline",
                "engine": "discoverex",
                "job_name": "prefect-smoke",
                "inputs": {
                    "contract_version": "v2",
                    "command": "animate",
                    "args": {},
                },
                "env": {"X_TEST_ENV": "1"},
            },
            ensure_ascii=True,
        )
    )

    assert captured["cmd"][0:3] == [
        sys.executable,
        "-m",
        "discoverex.orchestrator_contract.launcher",
    ]
    assert captured["cwd"] == Path(__file__).resolve().parents[1]
    assert captured["env"]["ORCH_JOB_INPUTS_JSON"]
    assert captured["env"]["ORCH_ENGINE_ARTIFACT_DIR"]
    assert captured["env"]["ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"]
    assert captured["env"]["PYTHONPATH"].startswith(
        str(Path(__file__).resolve().parents[1] / "src")
    )
    assert json.loads(captured["env"]["ORCH_JOB_INPUTS_JSON"]) == {
        "run_mode": "inline",
        "engine": "discoverex",
        "job_name": "prefect-smoke",
        "inputs": {
            "contract_version": "v2",
            "command": "animate",
            "args": {},
        },
        "env": {"X_TEST_ENV": "1"},
    }
    assert output["status"] == "ok"
    assert output["job_name"] == "prefect-smoke"
    assert output["engine"] == "discoverex"
    assert output["run_mode"] == "inline"
    assert output["flow_run_id"] == "flow-123"
    assert output["attempt"] == 1
    assert output["outputs_prefix"] == "jobs/flow-123/attempt-1/"
    assert logged[0][0] == "engine flow start: %s"
    assert logged[-1][0] == "launcher payload summary: %s"
    assert "prefect-smoke" in str(logged[-1][1])
    assert "[discoverex-engine-flow] start" in capsys.readouterr().err


def test_run_launcher_process_streams_logs_and_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logged: list[tuple[str, tuple[Any, ...]]] = []

    class _FakeStream:
        def __init__(self, lines: list[str]) -> None:
            self._lines = iter(lines)

        def readline(self) -> str:
            return next(self._lines, "")

        def close(self) -> None:
            return None

    class _FakePopen:
        def __init__(self, *_: object, **__: object) -> None:
            self.stdout = _FakeStream(
                [
                    "child stdout line\n",
                    '{"status":"ok","scene_id":"scene-1"}\n',
                ]
            )
            self.stderr = _FakeStream(
                [
                    "child stderr line\n",
                    '[discoverex-progress] {"event":"stage","stage":"object_inpaint","status":"started","region_id":"r-1"}\n',
                ]
            )

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(prefect_flow, "Popen", _FakePopen)

    execution = prefect_flow._run_launcher_process(
        cmd=["python", "-m", "x"],
        cwd=Path.cwd(),
        env={},
        logger=_FakeLogger(logged),
    )

    assert execution.returncode == 0
    assert "child stdout line" in execution.stdout
    assert "child stderr line" in execution.stderr
    assert execution.progress_events[-1]["stage"] == "object_inpaint"
    assert execution.stage_logs["launcher_start"].startswith("[stdout] child stdout line")
    assert execution.last_stage == "object_inpaint"
    assert any(msg == "stage %s %s" and args[0] == "object_inpaint" for msg, args in logged)


def test_repo_root_prefect_entrypoint_uploads_worker_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        prefect_flow,
        "_run_launcher_process",
        lambda **kwargs: prefect_flow.LauncherExecution(
            returncode=0,
            stdout='{"status":"ok","scene_id":"s1","version_id":"v1"}\n',
            stderr="",
        ),
    )
    monkeypatch.setattr(prefect_flow, "get_run_logger", lambda: _FakeLogger([]))
    monkeypatch.setattr(prefect_flow.flow_run, "get_id", lambda: "flow-456")
    monkeypatch.setattr(
        prefect_flow,
        "_upload_worker_artifacts",
        lambda **kwargs: {
            "stdout_uri": "s3://bucket/jobs/flow-456/attempt-1/stdout.log",
            "stderr_uri": "s3://bucket/jobs/flow-456/attempt-1/stderr.log",
            "result_uri": "s3://bucket/jobs/flow-456/attempt-1/result.json",
            "manifest_uri": "s3://bucket/jobs/flow-456/attempt-1/artifacts.json",
            "engine_manifest_uri": "s3://bucket/jobs/flow-456/attempt-1/engine-artifacts.json",
            "engine_artifact_uris": {
                "scene": "s3://bucket/jobs/flow-456/attempt-1/engine/scene/scene.json"
            },
        },
    )

    output = prefect_flow.run_job_flow.fn(
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
    assert output["engine_artifact_uris"]["scene"].endswith("/scene/scene.json")


def test_repo_root_prefect_entrypoint_surfaces_launcher_output_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        prefect_flow,
        "_run_launcher_process",
        lambda **kwargs: prefect_flow.LauncherExecution(
            returncode=2,
            stdout="boot log\nlast stdout line\n",
            stderr="last stderr line\n",
            progress_events=[
                {
                    "event": "stage",
                    "stage": "object_inpaint",
                    "status": "started",
                    "region_id": "r-1",
                }
            ],
            stage_logs={"object_inpaint": "[stderr] object failed badly"},
            last_stage="object_inpaint",
        ),
    )
    monkeypatch.setattr(prefect_flow, "get_run_logger", lambda: _FakeLogger([]))

    with pytest.raises(RuntimeError) as exc_info:
        prefect_flow.run_job_flow.fn(
            json.dumps(
                {
                    "run_mode": "inline",
                    "engine": "discoverex",
                    "inputs": {
                        "contract_version": "v2",
                        "command": "animate",
                        "args": {},
                    },
                },
                ensure_ascii=True,
            )
        )

    assert "launcher exited with status code 2" in str(exc_info.value)
    assert '"stage": "object_inpaint"' in str(exc_info.value)
    assert "failed stage: object_inpaint" in str(exc_info.value)
    assert "object failed badly" in str(exc_info.value)
    stderr_text = capsys.readouterr().err
    assert "[discoverex-engine-flow] failure-context" in stderr_text
    assert "Traceback" in stderr_text


def test_repo_root_prefect_entrypoint_raises_on_failed_child_payload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        prefect_flow,
        "_run_launcher_process",
        lambda **kwargs: prefect_flow.LauncherExecution(
            returncode=0,
            stdout='{"status":"failed","failure_reason":"boom","scene_json":""}\n',
            stderr="",
            progress_events=[
                {
                    "event": "stage",
                    "stage": "verification",
                    "status": "completed",
                    "passed": False,
                }
            ],
        ),
    )
    monkeypatch.setattr(prefect_flow, "get_run_logger", lambda: _FakeLogger([]))

    with pytest.raises(RuntimeError) as exc_info:
        prefect_flow.run_job_flow.fn(
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

    assert "launcher returned failed payload" in str(exc_info.value)
    assert "boom" in str(exc_info.value)
    stderr_text = capsys.readouterr().err
    assert "[discoverex-engine-flow] failure-context" in stderr_text
