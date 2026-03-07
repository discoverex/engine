from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError

from discoverex.orchestrator_contract.runner import build_cli_tokens
from discoverex.orchestrator_contract.schema import (
    BootstrapMode,
    OrchestratorInputsV1,
)

INPUTS_ENV = "ORCH_JOB_INPUTS_JSON"


class LauncherError(RuntimeError):
    pass


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> int:
    proc = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    return int(proc.returncode)


def _load_inputs_from_env() -> OrchestratorInputsV1:
    raw = os.getenv(INPUTS_ENV, "").strip()
    if not raw:
        raise LauncherError(f"missing required env: {INPUTS_ENV}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LauncherError(f"invalid JSON in {INPUTS_ENV}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LauncherError(f"{INPUTS_ENV} must be a JSON object")
    try:
        return OrchestratorInputsV1.model_validate(payload)
    except ValidationError as exc:
        raise LauncherError(f"invalid orchestrator inputs: {exc}") from exc


def _pick_mode(mode: BootstrapMode) -> BootstrapMode:
    if mode in {"uv", "pip"}:
        return mode
    if shutil.which("uv"):
        return "uv"
    return "pip"


def _venv_bin(cwd: Path, name: str) -> str:
    return str(cwd / ".venv" / "bin" / name)


def _prepare_env(cwd: Path, extra_env: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(extra_env)
    env["UV_CACHE_DIR"] = env.get("UV_CACHE_DIR", str(cwd / ".cache" / "uv"))
    Path(env["UV_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
    return env


def _bootstrap_with_uv(
    *,
    cwd: Path,
    env: dict[str, str],
    extras: list[str],
) -> None:
    if not shutil.which("uv"):
        raise LauncherError("bootstrap_mode=uv requested but uv is not installed")
    if not (cwd / ".venv").exists():
        if _run(["uv", "venv", ".venv"], cwd=cwd, env=env) != 0:
            raise LauncherError("uv venv failed")
    cmd = ["uv", "sync"]
    for extra in extras:
        cmd.extend(["--extra", extra])
    if _run(cmd, cwd=cwd, env=env) != 0:
        raise LauncherError("uv sync failed")


def _bootstrap_with_pip(
    *,
    cwd: Path,
    env: dict[str, str],
    extras: list[str],
) -> None:
    if not (cwd / ".venv").exists():
        if _run([sys.executable, "-m", "venv", ".venv"], cwd=cwd, env=env) != 0:
            raise LauncherError("python -m venv failed")
    pip_bin = _venv_bin(cwd, "pip")
    extra_suffix = f"[{','.join(extras)}]" if extras else ""
    if _run([pip_bin, "install", "-e", f".{extra_suffix}"], cwd=cwd, env=env) != 0:
        raise LauncherError("pip install failed")


def _run_job_with_uv(*, cwd: Path, env: dict[str, str], cli_tokens: list[str]) -> int:
    return _run(["uv", "run", *cli_tokens], cwd=cwd, env=env)


def _run_job_with_pip(*, cwd: Path, env: dict[str, str], cli_tokens: list[str]) -> int:
    discoverex_bin = _venv_bin(cwd, "discoverex")
    if len(cli_tokens) < 2 or cli_tokens[0] != "discoverex":
        raise LauncherError("invalid CLI tokens built for discoverex")
    return _run([discoverex_bin, *cli_tokens[1:]], cwd=cwd, env=env)


def run_orchestrator_job(cwd: Path | None = None) -> int:
    job = _load_inputs_from_env()
    run_cwd = cwd or Path.cwd()
    env = _prepare_env(run_cwd, job.runtime.extra_env)
    mode = _pick_mode(job.runtime.bootstrap_mode)
    if mode == "uv":
        _bootstrap_with_uv(cwd=run_cwd, env=env, extras=job.runtime.extras)
        return _run_job_with_uv(cwd=run_cwd, env=env, cli_tokens=build_cli_tokens(job))
    _bootstrap_with_pip(cwd=run_cwd, env=env, extras=job.runtime.extras)
    return _run_job_with_pip(cwd=run_cwd, env=env, cli_tokens=build_cli_tokens(job))


def main() -> None:
    try:
        code = run_orchestrator_job()
    except LauncherError as exc:
        print(f"[discoverex-orch-launcher] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
