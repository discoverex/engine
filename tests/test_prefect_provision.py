from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import infra.prefect.provision as provision


def test_provision_runtime_dependencies_uses_uv_sync_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str], check: bool) -> object:
        calls.append((cmd, env.copy()))
        assert cwd == tmp_path
        assert check is False
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(subprocess, "run", fake_run)

    provision.provision_runtime_dependencies(
        payload={
            "runtime": {
                "mode": "worker",
                "bootstrap_mode": "auto",
                "extras": ["tracking", "storage"],
            }
        },
        cwd=tmp_path,
        env={},
        logger=_FakeLogger(),
    )

    assert calls[0][0] == [
        "uv",
        "sync",
        "--active",
        "--frozen",
        "--extra",
        "tracking",
        "--extra",
        "storage",
    ]
    assert calls[0][1]["VIRTUAL_ENV"] == sys.prefix
    assert calls[0][1]["UV_PROJECT_ENVIRONMENT"] == sys.prefix


def test_provision_runtime_dependencies_falls_back_to_pip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", lambda name: None)

    def fake_run(cmd: list[str], *, cwd: Path, env: dict[str, str], check: bool) -> object:
        calls.append(cmd)
        assert cwd == tmp_path
        assert check is False
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(subprocess, "run", fake_run)

    provision.provision_runtime_dependencies(
        payload={
            "runtime": {
                "mode": "worker",
                "bootstrap_mode": "auto",
                "extras": ["tracking"],
            }
        },
        cwd=tmp_path,
        env={},
        logger=_FakeLogger(),
    )

    assert calls[0] == [sys.executable, "-m", "pip", "install", "-e", ".[tracking]"]


def test_provision_runtime_dependencies_skips_non_worker_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("subprocess.run should not be called"),
    )

    provision.provision_runtime_dependencies(
        payload={"runtime": {"mode": "local"}},
        cwd=tmp_path,
        env={},
        logger=_FakeLogger(),
    )


class _FakeLogger:
    def info(self, message: str, *args: object) -> None:
        return None
