from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal, cast

from discoverex.cache_dirs import resolve_cache_root, resolve_model_cache_dir, resolve_uv_cache_dir

BootstrapModeName = Literal["auto", "uv", "pip"]


def provision_runtime_dependencies(
    *,
    payload: dict[str, Any],
    cwd: Path,
    env: dict[str, str],
    logger: Any,
) -> None:
    runtime = _runtime_payload(payload)
    if str(runtime.get("mode", "")).strip() != "worker":
        return
    mode = _pick_mode(_runtime_bootstrap_mode(runtime))
    extras = _runtime_extras(runtime)
    logger.info(
        "engine dependency bootstrap: mode=%s extras=%s python=%s",
        mode,
        extras,
        sys.executable,
    )
    if mode == "uv":
        _bootstrap_with_uv(cwd=cwd, env=env, extras=extras, logger=logger)
    else:
        _bootstrap_with_pip(cwd=cwd, env=env, extras=extras, logger=logger)
    _activate_repo_environment(cwd=cwd, logger=logger)
    importlib.invalidate_caches()


def _runtime_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = payload.get("runtime", {})
    if not isinstance(runtime, dict):
        raise RuntimeError("inputs.runtime must be a JSON object")
    return runtime


def _runtime_bootstrap_mode(runtime: dict[str, Any]) -> BootstrapModeName:
    mode = str(runtime.get("bootstrap_mode", "auto")).strip() or "auto"
    if mode not in {"auto", "uv", "pip"}:
        raise RuntimeError(f"unsupported bootstrap_mode={mode}")
    return cast(BootstrapModeName, mode)


def _runtime_extras(runtime: dict[str, Any]) -> list[str]:
    extras = runtime.get("extras", [])
    if not isinstance(extras, list):
        raise RuntimeError("runtime.extras must be a JSON array")
    cleaned: list[str] = []
    for item in extras:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _pick_mode(mode: BootstrapModeName) -> BootstrapModeName:
    if mode in {"uv", "pip"}:
        return mode
    if shutil.which("uv"):
        return "uv"
    return "pip"


def _bootstrap_with_uv(
    *,
    cwd: Path,
    env: dict[str, str],
    extras: list[str],
    logger: Any,
) -> None:
    if not shutil.which("uv"):
        raise RuntimeError("bootstrap_mode=uv requested but uv is not installed")
    cmd = ["uv", "sync"]
    if (cwd / "uv.lock").exists():
        cmd.append("--frozen")
    for extra in extras:
        cmd.extend(["--extra", extra])
    install_env = _install_env(env, cwd)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=install_env,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _log_subprocess_failure(logger, cmd=cmd, result=result)
        raise RuntimeError(f"{' '.join(cmd)} failed")


def _bootstrap_with_pip(
    *,
    cwd: Path,
    env: dict[str, str],
    extras: list[str],
    logger: Any,
) -> None:
    spec = "."
    if extras:
        spec = f".[{','.join(extras)}]"
    cmd = [sys.executable, "-m", "pip", "install", "-e", spec]
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=_install_env(env, cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _log_subprocess_failure(logger, cmd=cmd, result=result)
        raise RuntimeError(f"{' '.join(cmd)} failed")


def _install_env(env: dict[str, str], cwd: Path) -> dict[str, str]:
    install_env = env.copy()
    cache_root = resolve_cache_root(default_base=cwd / ".cache")
    install_env.setdefault("CACHE_DIR", str(cache_root))
    install_env["UV_CACHE_DIR"] = str(resolve_uv_cache_dir(default_base=cache_root))
    install_env.setdefault(
        "MODEL_CACHE_DIR",
        str(resolve_model_cache_dir(default_base=cache_root)),
    )
    install_env.pop("VIRTUAL_ENV", None)
    install_env["UV_PROJECT_ENVIRONMENT"] = str(cwd / ".venv")
    Path(install_env["UV_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(install_env["MODEL_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    return install_env


def _activate_repo_environment(*, cwd: Path, logger: Any) -> None:
    inserted: list[str] = []
    src_dir = cwd / "src"
    if src_dir.exists():
        _prepend_sys_path(src_dir, inserted)
    for site_packages in sorted((cwd / ".venv" / "lib").glob("python*/site-packages")):
        if site_packages.exists():
            _prepend_sys_path(site_packages, inserted)
    if inserted:
        logger.info("activated repo runtime paths: %s", inserted)
    os.environ["PYTHONPATH"] = ":".join(
        [str(src_dir), os.environ.get("PYTHONPATH", "").strip()]
    ).rstrip(":")


def _prepend_sys_path(path: Path, inserted: list[str]) -> None:
    text = str(path)
    if text in sys.path:
        return
    sys.path.insert(0, text)
    inserted.append(text)


def _log_subprocess_failure(logger: Any, *, cmd: list[str], result: Any) -> None:
    stdout = str(getattr(result, "stdout", "") or "").strip()
    stderr = str(getattr(result, "stderr", "") or "").strip()
    logger.error(
        "dependency bootstrap command failed: %s (exit_code=%s)",
        " ".join(cmd),
        getattr(result, "returncode", ""),
    )
    if stdout:
        logger.error("dependency bootstrap stdout:\n%s", stdout)
    if stderr:
        logger.error("dependency bootstrap stderr:\n%s", stderr)
