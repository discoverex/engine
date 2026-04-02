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
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("subprocess.run should not be called"),
    )
    src_dir = tmp_path / "src"
    site_packages = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
    src_dir.mkdir(parents=True)
    site_packages.mkdir(parents=True)

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

    assert str(src_dir) in sys.path
    assert str(site_packages) in sys.path


def test_provision_runtime_dependencies_falls_back_to_pip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("subprocess.run should not be called"),
    )
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)

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

    assert str(src_dir) in sys.path


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


def test_provision_runtime_dependencies_skips_bootstrap_for_none_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("subprocess.run should not be called"),
    )
    src_dir = tmp_path / "src"
    site_packages = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
    src_dir.mkdir(parents=True)
    site_packages.mkdir(parents=True)

    provision.provision_runtime_dependencies(
        payload={"runtime": {"mode": "worker", "bootstrap_mode": "none"}},
        cwd=tmp_path,
        env={},
        logger=_FakeLogger(),
    )


def test_install_env_respects_explicit_uv_project_environment(tmp_path: Path) -> None:
    mounted_venv = tmp_path / "mounted" / ".venv"

    install_env = provision._install_env(
        {"UV_PROJECT_ENVIRONMENT": str(mounted_venv)},
        tmp_path,
    )

    assert install_env["UV_PROJECT_ENVIRONMENT"] == str(mounted_venv)


class _FakeLogger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, tuple[object, ...]]] = []

    def info(self, message: str, *args: object) -> None:
        return None

    def error(self, message: str, *args: object) -> None:
        self.errors.append((message, args))


def test_provision_runtime_dependencies_logs_uv_failure_details(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")
    logger = _FakeLogger()

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> object:
        _ = (cmd, cwd, env, check, capture_output, text)
        return type(
            "Result",
            (),
            {
                "returncode": 1,
                "stdout": "Prepared 98 packages in 1m 25s",
                "stderr": "error: failed to remove file `/opt/venv/lib/python3.11/site-packages/argon2/__init__.py`: Permission denied",
            },
        )()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="uv sync --extra tracking failed"):
        provision.provision_runtime_dependencies(
            payload={
                "runtime": {
                    "mode": "worker",
                    "bootstrap_mode": "uv",
                    "extras": ["tracking"],
                }
            },
            cwd=tmp_path,
            env={},
            logger=logger,
        )

    assert (
        logger.errors[0][0] == "dependency bootstrap command failed: %s (exit_code=%s)"
    )
    assert logger.errors[1][0] == "dependency bootstrap stdout:\n%s"
    assert "Prepared 98 packages" in str(logger.errors[1][1][0])
    assert logger.errors[2][0] == "dependency bootstrap stderr:\n%s"
    assert "Permission denied" in str(logger.errors[2][1][0])


def test_provision_runtime_dependencies_activates_repo_runtime_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/uv")
    src_dir = tmp_path / "src"
    site_packages = tmp_path / ".venv" / "lib" / "python3.11" / "site-packages"
    src_dir.mkdir(parents=True)
    site_packages.mkdir(parents=True)
    logger = _FakeLogger()

    def fake_run(
        cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> object:
        _ = (cmd, cwd, env, check, capture_output, text)
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(subprocess, "run", fake_run)
    original_sys_path = list(sys.path)
    monkeypatch.setattr(sys, "path", list(sys.path))

    provision.provision_runtime_dependencies(
        payload={
            "runtime": {
                "mode": "worker",
                "bootstrap_mode": "uv",
                "extras": [],
            }
        },
        cwd=tmp_path,
        env={},
        logger=logger,
    )

    assert str(src_dir) in sys.path
    assert str(site_packages) in sys.path
    assert logger.errors == []
    monkeypatch.setattr(sys, "path", original_sys_path)
