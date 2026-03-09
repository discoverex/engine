from __future__ import annotations

import json
from pathlib import Path

import pytest

import discoverex.orchestrator_contract.launcher as launcher


def _job_payload(runtime: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {
        "contract_version": "v2",
        "command": "generate",
        "args": {"background_asset_ref": "bg://dummy"},
    }
    if runtime is not None:
        payload["runtime"] = runtime
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
    assert calls[2][0:3] == ["uv", "run", "discoverex"]
    assert "generate" in calls[2]


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
    assert calls[2][0].endswith("/.venv/bin/discoverex")
    assert "generate" in calls[2]


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
    assert calls[2][0:4] == ["uv", "run", "discoverex", "verify"]


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
                    "MLFLOW_TRACKING_URI": "http://mlflow.local:5000",
                    "ARTIFACT_BUCKET": "orchestrator-artifacts",
                }
            }
        ),
    )
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
    assert discoverex_env["MLFLOW_TRACKING_URI"] == "http://mlflow.local:5000"
    assert discoverex_env["ARTIFACT_BUCKET"] == "orchestrator-artifacts"
