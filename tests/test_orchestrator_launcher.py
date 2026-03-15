from __future__ import annotations

import json
from pathlib import Path

import pytest

import discoverex.orchestrator_contract.launcher as launcher
from discoverex.progress_events import parse_progress_event_line


def _job_payload(runtime: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {
        "contract_version": "v2",
        "command": "generate",
        "config_name": "generate_gpu",
        "config_dir": "/workspace/conf",
        "args": {"background_asset_ref": "bg://dummy"},
    }
    if runtime is not None:
        payload["runtime"] = runtime
    return json.dumps(payload, ensure_ascii=True)


def _wrapper_payload(runtime: dict[str, object] | None = None) -> str:
    inputs: dict[str, object] = {
        "contract_version": "v2",
        "command": "generate",
        "config_name": "generate_gpu",
        "config_dir": "/workspace/conf",
        "args": {"background_asset_ref": "bg://dummy"},
    }
    if runtime is not None:
        inputs["runtime"] = runtime
    payload = {
        "run_mode": "inline",
        "engine": "discoverex",
        "entrypoint": [
            "/bin/sh",
            "-lc",
            "PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher",
        ],
        "inputs": inputs,
        "env": {},
        "outputs_prefix": None,
    }
    return json.dumps(payload, ensure_ascii=True)


def test_run_orchestrator_job_uses_uv_path_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    monkeypatch.setenv("ORCH_JOB_INPUTS_JSON", _job_payload())
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append(cmd)
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    assert calls[0] == ["uv", "venv", ".venv"]
    assert calls[1] == ["uv", "sync", "--extra", "tracking", "--extra", "storage"]
    assert calls[2][0].endswith("/.venv/bin/python")
    assert calls[2][1:3] == ["-m", "discoverex.application.flows.launcher_entry"]


def test_run_orchestrator_job_falls_back_to_pip_when_uv_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    monkeypatch.setenv("ORCH_JOB_INPUTS_JSON", _job_payload())
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: None,
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append(cmd)
        if cmd[-1] == ".venv":
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        if cmd[0].endswith("/pip"):
            discoverex = cwd / ".venv" / "bin" / "discoverex"
            discoverex.parent.mkdir(parents=True, exist_ok=True)
            discoverex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    assert calls[0][1:4] == ["-m", "venv", ".venv"]
    assert calls[1][1:3] == ["install", "-e"]
    assert calls[2][0].endswith("/.venv/bin/python")
    assert calls[2][1:3] == ["-m", "discoverex.application.flows.launcher_entry"]


def test_run_orchestrator_job_supports_v1_command_shim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    monkeypatch.setenv(
        "ORCH_JOB_INPUTS_JSON",
        json.dumps(
            {
                "contract_version": "v1",
                "command": "verify-only",
                "args": {"scene_json": "/tmp/scene.json"},
            },
            ensure_ascii=True,
        ),
    )
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append(cmd)
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    assert calls[2][0].endswith("/.venv/bin/python")
    assert calls[2][1:3] == ["-m", "discoverex.application.flows.launcher_entry"]


def test_run_orchestrator_job_warns_for_legacy_v1(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(
        "ORCH_JOB_INPUTS_JSON",
        json.dumps(
            {
                "contract_version": "v1",
                "command": "gen-verify",
                "args": {"background_asset_ref": "bg://dummy"},
            },
            ensure_ascii=True,
        ),
    )
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    err = capsys.readouterr().err
    assert "deprecated command set (v1)" in err


def test_run_orchestrator_job_fails_for_invalid_inputs_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORCH_JOB_INPUTS_JSON", raising=False)
    with pytest.raises(launcher.LauncherError, match="missing required env"):
        launcher.run_orchestrator_job()


def test_run_orchestrator_job_passes_runtime_extra_env_to_discoverex(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    monkeypatch.setenv(
        "ORCH_JOB_INPUTS_JSON",
        _job_payload(
            runtime={
                "extra_env": {
                    "MLFLOW_TRACKING_URI": "https://mlflow.example.com",
                    "ARTIFACT_BUCKET": "orchestrator-artifacts",
                }
            }
        ),
    )
    monkeypatch.setenv("MLFLOW_TRACKING_PROXY_URL", "http://127.0.0.1:15000")
    monkeypatch.setenv("PREFECT_API_URL", "https://prefect-api.discoverex.qzz.io/api")
    monkeypatch.setenv("cf_access_client_id", "worker-only-id")
    monkeypatch.setenv("cf_access_client_secret", "worker-only-secret")
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append((cmd, env.copy()))
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    _, discoverex_env = calls[2]
    assert discoverex_env["MLFLOW_TRACKING_URI"] == "http://127.0.0.1:15000"
    assert discoverex_env["ARTIFACT_BUCKET"] == "orchestrator-artifacts"
    assert discoverex_env["PREFECT_API_URL"] == ""
    assert discoverex_env["PREFECT_EVENTS_ENABLED"] == "false"
    assert discoverex_env["PREFECT_SERVER_ALLOW_EPHEMERAL_MODE"] == "true"
    assert discoverex_env["PREFECT_LOGGING_TO_API_ENABLED"] == "false"
    assert "cf_access_client_id" not in discoverex_env
    assert "cf_access_client_secret" not in discoverex_env
    assert "MLFLOW_TRACKING_PROXY_URL" not in discoverex_env


def test_run_orchestrator_job_emits_bootstrap_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ORCH_JOB_INPUTS_JSON", _job_payload())
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)

    assert code == 0
    events = [
        event
        for event in (
            parse_progress_event_line(line)
            for line in capsys.readouterr().err.splitlines()
        )
        if event is not None
    ]
    assert [event["stage"] for event in events[:6]] == [
        "launcher_start",
        "bootstrap_env",
        "bootstrap_venv",
        "bootstrap_venv",
        "bootstrap_sync",
        "bootstrap_sync",
    ]


def test_run_orchestrator_job_accepts_wrapper_payload_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    raw_wrapper = _wrapper_payload()
    monkeypatch.setenv("ORCH_JOB_INPUTS_JSON", _wrapper_payload())
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append((cmd, env.copy()))
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    assert calls[2][0][0].endswith("/.venv/bin/python")
    assert calls[2][0][1:3] == ["-m", "discoverex.application.flows.launcher_entry"]
    assert json.loads(calls[2][1]["ORCH_JOB_INPUTS_JSON"]) == json.loads(raw_wrapper)


def test_run_orchestrator_job_accepts_legacy_engine_run_wrapper_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv(
        "ORCH_JOB_INPUTS_JSON",
        json.dumps(
            {
                "run_mode": "inline",
                "engine": "discoverex",
                "entrypoint": [
                    "/bin/sh",
                    "-lc",
                    "PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher",
                ],
                "engine_run": {
                    "contract_version": "v2",
                    "command": "generate",
                    "args": {"background_asset_ref": "bg://dummy"},
                },
            },
            ensure_ascii=True,
        ),
    )
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append(cmd)
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    assert calls[2][0].endswith("/.venv/bin/python")
    assert calls[2][1:3] == ["-m", "discoverex.application.flows.launcher_entry"]
    assert "deprecated wrapper payload" in capsys.readouterr().err


def test_run_orchestrator_job_fails_when_remote_tracking_uri_has_no_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "ORCH_JOB_INPUTS_JSON",
        _job_payload(
            runtime={"extra_env": {"MLFLOW_TRACKING_URI": "https://mlflow.example.com"}}
        ),
    )
    monkeypatch.delenv("MLFLOW_TRACKING_PROXY_URL", raising=False)
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    with pytest.raises(
        launcher.LauncherError, match="MLFLOW_TRACKING_URI is a remote URL"
    ):
        launcher.run_orchestrator_job(cwd=tmp_path)


def test_run_orchestrator_job_allows_localhost_tracking_uri_without_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    monkeypatch.setenv(
        "ORCH_JOB_INPUTS_JSON",
        _job_payload(
            runtime={"extra_env": {"MLFLOW_TRACKING_URI": "http://127.0.0.1:5000"}}
        ),
    )
    monkeypatch.delenv("MLFLOW_TRACKING_PROXY_URL", raising=False)
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append((cmd, env.copy()))
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    _, discoverex_env = calls[2]
    assert discoverex_env["MLFLOW_TRACKING_URI"] == "http://127.0.0.1:5000"


def test_run_orchestrator_job_accepts_background_prompt_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv(
        "ORCH_JOB_INPUTS_JSON",
        json.dumps(
            {
                "contract_version": "v2",
                "command": "generate",
                "args": {"background_prompt": "moonlit forest"},
            },
            ensure_ascii=True,
        ),
    )
    monkeypatch.setattr(
        "discoverex.orchestrator_contract.launcher.shutil.which",
        lambda _name: "/usr/bin/uv",
    )

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
        calls.append(cmd)
        if cmd[0:2] == ["uv", "venv"]:
            (cwd / ".venv").mkdir(parents=True, exist_ok=True)
        return 0

    monkeypatch.setattr(launcher, "_run", fake_run)

    code = launcher.run_orchestrator_job(cwd=tmp_path)
    assert code == 0
    assert calls[2][0].endswith("/.venv/bin/python")
    assert calls[2][1:3] == ["-m", "discoverex.application.flows.launcher_entry"]
