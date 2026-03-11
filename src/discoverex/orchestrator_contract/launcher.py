from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

BootstrapModeName = Literal["auto", "uv", "pip"]

INPUTS_ENV = "ORCH_JOB_INPUTS_JSON"
_WORKER_ONLY_ENV_KEYS = {
    "CF_ACCESS_CLIENT_ID",
    "CF_ACCESS_CLIENT_SECRET",
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
    engine_run = raw_payload.get("engine_run")
    if engine_run is not None:
        if not isinstance(engine_run, dict):
            raise LauncherError("engine_run must be a JSON object")
        return engine_run
    legacy_inputs = raw_payload.get("inputs")
    if legacy_inputs is not None:
        if not isinstance(legacy_inputs, dict):
            raise LauncherError("inputs must be a JSON object")
        print(
            "[discoverex-orch-launcher] deprecated wrapper payload: "
            "use engine_run instead of inputs",
            file=sys.stderr,
        )
        return legacy_inputs
    return raw_payload


def _runtime_payload(raw_payload: dict[str, object]) -> dict[str, object]:
    runtime = raw_payload.get("runtime")
    if runtime is None:
        return {}
    if not isinstance(runtime, dict):
        raise LauncherError("runtime must be a JSON object")
    return runtime


def _runtime_extras(raw_payload: dict[str, object]) -> list[str]:
    runtime = _runtime_payload(raw_payload)
    extras = runtime.get("extras", ["tracking", "storage"])
    if not isinstance(extras, list):
        raise LauncherError("runtime.extras must be a list")
    cleaned: list[str] = []
    for item in extras:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _runtime_extra_env(raw_payload: dict[str, object]) -> dict[str, str]:
    runtime = _runtime_payload(raw_payload)
    extra_env = runtime.get("extra_env", {})
    if not isinstance(extra_env, dict):
        raise LauncherError("runtime.extra_env must be a JSON object")
    return {str(key): str(value) for key, value in extra_env.items()}


def _runtime_bootstrap_mode(raw_payload: dict[str, object]) -> BootstrapModeName:
    runtime = _runtime_payload(raw_payload)
    mode = str(runtime.get("bootstrap_mode", "auto")).strip() or "auto"
    if mode not in {"auto", "uv", "pip"}:
        raise LauncherError(f"unsupported bootstrap_mode={mode}")
    return mode


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
    *,
    target_name: str,
    upstream_url: str,
    proxy_url: str,
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
        raise LauncherError(f"unsupported contract_version={contract_version or '<empty>'}")

    command = str(raw_payload.get("command", "")).strip()
    required_by_command: dict[str, dict[str, tuple[str, ...]]] = {
        "v1": {
            "gen-verify": (),
            "verify-only": ("scene_json",),
            "replay-eval": ("scene_jsons",),
        },
        "v2": {
            "generate": (),
            "verify": ("scene_json",),
            "animate": (),
        },
    }
    if command not in required_by_command[contract_version]:
        raise LauncherError(f"unsupported command={command or '<empty>'}")

    args = raw_payload.get("args", {})
    if not isinstance(args, dict):
        raise LauncherError("args must be a JSON object")
    missing = [key for key in required_by_command[contract_version][command] if key not in args]
    if missing:
        missing_str = ", ".join(missing)
        raise LauncherError(
            f"missing required args for command={command}: {missing_str}"
        )
    if command in {"gen-verify", "generate"}:
        background_asset_ref = str(args.get("background_asset_ref", "")).strip()
        background_prompt = str(args.get("background_prompt", "")).strip()
        if not background_asset_ref and not background_prompt:
            raise LauncherError(
                f"missing required args for command={command}: "
                "background_asset_ref or background_prompt"
            )

    overrides = raw_payload.get("overrides", [])
    if not isinstance(overrides, list):
        raise LauncherError("overrides must be a JSON list")
    for key in ("config_name", "config_dir"):
        value = raw_payload.get(key)
        if value is not None and not isinstance(value, str):
            raise LauncherError(f"{key} must be a string")


def _is_legacy_command(raw_payload: dict[str, object]) -> bool:
    return str(raw_payload.get("contract_version", "")).strip() == "v1"


def _mapped_command(raw_payload: dict[str, object]) -> str:
    command = str(raw_payload.get("command", "")).strip()
    if not _is_legacy_command(raw_payload):
        return command
    return {
        "gen-verify": "generate",
        "verify-only": "verify",
        "replay-eval": "animate",
    }[command]


def _append_arg(tokens: list[str], key: str, value: object) -> None:
    if value is None:
        return
    flag = f"--{key.replace('_', '-')}"
    if isinstance(value, bool):
        if value:
            tokens.append(flag)
        return
    if isinstance(value, str):
        tokens.extend([flag, value])
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            tokens.extend([flag, str(item)])
        return
    tokens.extend([flag, str(value)])


def _build_cli_tokens(raw_payload: dict[str, object]) -> list[str]:
    args = raw_payload.get("args", {})
    if not isinstance(args, dict):
        raise LauncherError("args must be a JSON object")
    overrides = raw_payload.get("overrides", [])
    if not isinstance(overrides, list):
        raise LauncherError("overrides must be a JSON list")

    tokens = ["discoverex", _mapped_command(raw_payload)]
    config_name = raw_payload.get("config_name")
    if isinstance(config_name, str) and config_name.strip():
        tokens.extend(["--config-name", config_name])
    config_dir = raw_payload.get("config_dir")
    if isinstance(config_dir, str) and config_dir.strip():
        tokens.extend(["--config-dir", config_dir])
    for key, value in args.items():
        _append_arg(tokens, str(key), value)
    for override in overrides:
        tokens.extend(["-o", str(override)])
    return tokens


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
    raw_payload = _extract_engine_run_spec(_load_raw_payload_from_env())
    _validate_contract(raw_payload)
    run_cwd = cwd or Path.cwd()
    env = _prepare_env(run_cwd, _runtime_extra_env(raw_payload))
    extras = _runtime_extras(raw_payload)
    mode = _pick_mode(_runtime_bootstrap_mode(raw_payload))
    if mode == "uv":
        _bootstrap_with_uv(cwd=run_cwd, env=env, extras=extras)
    else:
        _bootstrap_with_pip(cwd=run_cwd, env=env, extras=extras)
    cli_tokens = _build_cli_tokens(raw_payload)
    if _is_legacy_command(raw_payload):
        print(
            "[discoverex-orch-launcher] deprecated command set (v1): "
            "use contract_version=v2 with generate|verify|animate",
            file=sys.stderr,
        )
    if mode == "uv":
        return _run_job_with_uv(cwd=run_cwd, env=env, cli_tokens=cli_tokens)
    return _run_job_with_pip(cwd=run_cwd, env=env, cli_tokens=cli_tokens)


def main() -> None:
    try:
        code = run_orchestrator_job()
    except LauncherError as exc:
        print(f"[discoverex-orch-launcher] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(code)


if __name__ == "__main__":
    main()
