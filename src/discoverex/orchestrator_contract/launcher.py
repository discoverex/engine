from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse

from discoverex.progress_events import emit_progress_event

BootstrapModeName = Literal["auto", "uv", "pip"]

INPUTS_ENV = "ORCH_JOB_INPUTS_JSON"
_WORKER_ONLY_ENV_KEYS = {
    "cf_access_client_id",
    "cf_access_client_secret",
    "PREFECT_API_URL",
    "MLFLOW_TRACKING_PROXY_URL",
    "PREFECT_API_PROXY_URL",
}


class LauncherError(RuntimeError):
    pass


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
    proc = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    return int(proc.returncode)


def _load_raw_payload_from_env() -> dict[str, object]:
    raw = os.getenv(INPUTS_ENV, "").strip()
    if not raw:
        raise LauncherError(f"missing required env: {INPUTS_ENV}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LauncherError(f"invalid JSON in {INPUTS_ENV}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LauncherError(f"{INPUTS_ENV} must be a JSON object")
    return payload


def _extract_engine_run_spec(raw_payload: dict[str, object]) -> dict[str, object]:
    inputs = raw_payload.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict):
            raise LauncherError("inputs must be a JSON object")
        return inputs
    engine_run = raw_payload.get("engine_run")
    if engine_run is not None:
        if not isinstance(engine_run, dict):
            raise LauncherError("engine_run must be a JSON object")
        print(
            "[discoverex-execution-launcher] deprecated wrapper payload: use inputs instead of engine_run",
            file=sys.stderr,
        )
        return engine_run
    return raw_payload


def _runtime_payload(raw_payload: dict[str, object]) -> dict[str, object]:
    runtime = raw_payload.get("runtime")
    if runtime is None:
        return {}
    if not isinstance(runtime, dict):
        raise LauncherError("runtime must be a JSON object")
    return runtime


def _runtime_extras(engine_payload: dict[str, object]) -> list[str]:
    runtime = _runtime_payload(engine_payload)
    extras = runtime.get("extras", ["tracking", "storage"])
    if not isinstance(extras, list):
        raise LauncherError("runtime.extras must be a list")
    cleaned: list[str] = []
    for item in extras:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _runtime_extra_env(engine_payload: dict[str, object]) -> dict[str, str]:
    runtime = _runtime_payload(engine_payload)
    extra_env = runtime.get("extra_env", {})
    if not isinstance(extra_env, dict):
        raise LauncherError("runtime.extra_env must be a JSON object")
    return {str(key): str(value) for key, value in extra_env.items()}


def _runtime_bootstrap_mode(engine_payload: dict[str, object]) -> BootstrapModeName:
    runtime = _runtime_payload(engine_payload)
    mode = str(runtime.get("bootstrap_mode", "auto")).strip() or "auto"
    if mode not in {"auto", "uv", "pip"}:
        raise LauncherError(f"unsupported bootstrap_mode={mode}")
    return cast(BootstrapModeName, mode)


def _pick_mode(mode: BootstrapModeName) -> BootstrapModeName:
    if mode in {"uv", "pip"}:
        return mode
    if shutil.which("uv"):
        return "uv"
    return "pip"


def _venv_bin(cwd: Path, name: str) -> str:
    return str(cwd / ".venv" / "bin" / name)


def _prepare_env(cwd: Path, extra_env: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    for key in _WORKER_ONLY_ENV_KEYS:
        env.pop(key, None)
    env.update(extra_env)
    _rewrite_proxy_targets(env)
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", str(cwd / ".cache" / "uv"))
    env["UV_PROJECT_ENVIRONMENT"] = str(cwd / ".venv")
    env["PREFECT_API_URL"] = ""
    env["PREFECT_EVENTS_ENABLED"] = "false"
    env.setdefault("PREFECT_SERVER_ALLOW_EPHEMERAL_MODE", "true")
    env.setdefault("PREFECT_LOGGING_TO_API_ENABLED", "false")
    Path(env["UV_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    return env


def _rewrite_proxy_targets(env: dict[str, str]) -> None:
    tracking_uri = env.get("MLFLOW_TRACKING_URI", "").strip()
    if tracking_uri:
        env["MLFLOW_TRACKING_URI"] = _resolve_proxy_target(
            target_name="MLFLOW_TRACKING_URI",
            upstream_url=tracking_uri,
            proxy_url=os.getenv("MLFLOW_TRACKING_PROXY_URL", "").strip(),
        )


def _resolve_proxy_target(
    *, target_name: str, upstream_url: str, proxy_url: str
) -> str:
    if not _is_remote_url(upstream_url) or _is_local_mlflow_url(upstream_url):
        return upstream_url
    if not proxy_url:
        raise LauncherError(
            f"{target_name} is a remote URL but worker proxy is not configured"
        )
    return proxy_url


def _is_remote_url(value: str) -> bool:
    lower = value.lower()
    return lower.startswith("http://") or lower.startswith("https://")


def _is_local_mlflow_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1"}


def _validate_contract(raw_payload: dict[str, object]) -> None:
    contract_version = str(raw_payload.get("contract_version", "")).strip()
    if contract_version not in {"v1", "v2"}:
        raise LauncherError(
            f"unsupported contract_version={contract_version or '<empty>'}"
        )
    command = str(raw_payload.get("command", "")).strip()
    if command not in {
        "gen-verify",
        "verify-only",
        "replay-eval",
        "generate",
        "verify",
        "animate",
    }:
        raise LauncherError(f"unsupported command={command or '<empty>'}")


def _is_legacy_command(raw_payload: dict[str, object]) -> bool:
    return str(raw_payload.get("contract_version", "")).strip() == "v1"


def _bootstrap_with_uv(*, cwd: Path, env: dict[str, str], extras: list[str]) -> None:
    if not shutil.which("uv"):
        raise LauncherError("bootstrap_mode=uv requested but uv is not installed")
    emit_progress_event(stage="bootstrap_venv", status="started", mode="uv")
    if (
        not (cwd / ".venv").exists()
        and _run(["uv", "venv", ".venv"], cwd=cwd, env=env) != 0
    ):
        emit_progress_event(stage="bootstrap_venv", status="failed", mode="uv")
        raise LauncherError("uv venv failed")
    emit_progress_event(stage="bootstrap_venv", status="completed", mode="uv")
    cmd = ["uv", "sync"]
    for extra in extras:
        cmd.extend(["--extra", extra])
    emit_progress_event(
        stage="bootstrap_sync",
        status="started",
        mode="uv",
        extras=extras,
    )
    if _run(cmd, cwd=cwd, env=env) != 0:
        emit_progress_event(stage="bootstrap_sync", status="failed", mode="uv")
        raise LauncherError("uv sync failed")
    emit_progress_event(stage="bootstrap_sync", status="completed", mode="uv")


def _bootstrap_with_pip(*, cwd: Path, env: dict[str, str], extras: list[str]) -> None:
    emit_progress_event(stage="bootstrap_venv", status="started", mode="pip")
    if (
        not (cwd / ".venv").exists()
        and _run([sys.executable, "-m", "venv", ".venv"], cwd=cwd, env=env) != 0
    ):
        emit_progress_event(stage="bootstrap_venv", status="failed", mode="pip")
        raise LauncherError("python -m venv failed")
    emit_progress_event(stage="bootstrap_venv", status="completed", mode="pip")
    pip_bin = _venv_bin(cwd, "pip")
    extra_suffix = f"[{','.join(extras)}]" if extras else ""
    emit_progress_event(
        stage="bootstrap_sync",
        status="started",
        mode="pip",
        extras=extras,
    )
    if _run([pip_bin, "install", "-e", f".{extra_suffix}"], cwd=cwd, env=env) != 0:
        emit_progress_event(stage="bootstrap_sync", status="failed", mode="pip")
        raise LauncherError("pip install failed")
    emit_progress_event(stage="bootstrap_sync", status="completed", mode="pip")


def _run_job_with_python(*, cwd: Path, env: dict[str, str]) -> int:
    python_bin = _venv_bin(cwd, "python")
    return _run(
        [python_bin, "-m", "discoverex.application.flows.launcher_entry"],
        cwd=cwd,
        env=env,
    )


def run_orchestrator_job(cwd: Path | None = None) -> int:
    raw_payload = _load_raw_payload_from_env()
    engine_payload = _extract_engine_run_spec(raw_payload)
    _validate_contract(engine_payload)
    run_cwd = cwd or Path.cwd()
    emit_progress_event(stage="launcher_start", status="started")
    env = _prepare_env(run_cwd, _runtime_extra_env(engine_payload))
    emit_progress_event(stage="bootstrap_env", status="completed")
    extras = _runtime_extras(engine_payload)
    mode = _pick_mode(_runtime_bootstrap_mode(engine_payload))
    if mode == "uv":
        _bootstrap_with_uv(cwd=run_cwd, env=env, extras=extras)
    else:
        _bootstrap_with_pip(cwd=run_cwd, env=env, extras=extras)
    if _is_legacy_command(engine_payload):
        print(
            "[discoverex-execution-launcher] deprecated command set (v1): use contract_version=v2 with generate|verify|animate",
            file=sys.stderr,
        )
    emit_progress_event(stage="engine_exec", status="started")
    return _run_job_with_python(cwd=run_cwd, env=env)


def main() -> None:
    try:
        code = run_orchestrator_job()
    except LauncherError as exc:
        print(f"[discoverex-execution-launcher] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
