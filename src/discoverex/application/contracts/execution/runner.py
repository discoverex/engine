from __future__ import annotations

import shlex
from typing import Any

from discoverex.application.contracts.execution.schema import EngineRunSpec


def is_legacy_command(job: EngineRunSpec) -> bool:
    return job.contract_version == "v1"


def _to_flag(name: str) -> str:
    return f"--{name.replace('_', '-')}"


def _append_arg(tokens: list[str], key: str, value: Any) -> None:
    if value is None:
        return
    flag = _to_flag(key)
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


def _map_command_to_v2(job: EngineRunSpec) -> str:
    if not is_legacy_command(job):
        return job.command
    return {
        "gen-verify": "generate",
        "verify-only": "verify",
        "replay-eval": "animate",
    }[job.command]


def build_cli_tokens(job: EngineRunSpec) -> list[str]:
    tokens = ["discoverex", _map_command_to_v2(job)]
    if job.config_name:
        tokens.extend(["--config-name", job.config_name])
    if job.config_dir:
        tokens.extend(["--config-dir", job.config_dir])
    for key, value in job.args.items():
        _append_arg(tokens, key, value)
    for override in job.overrides:
        tokens.extend(["-o", override])
    return tokens


def build_worker_entrypoint(job: EngineRunSpec) -> list[str]:
    cli = shlex.join(build_cli_tokens(job))
    return ["/bin/sh", "-lc", f'UV_CACHE_DIR="$PWD/.cache/uv" uv run {cli}']
