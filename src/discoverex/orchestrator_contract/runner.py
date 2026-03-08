from __future__ import annotations

import shlex
from typing import Any

from discoverex.orchestrator_contract.schema import EngineJob


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


def _map_command_to_v2(job: EngineJob) -> str:
    if job.contract_version == "v2":
        return job.command
    legacy_map = {
        "gen-verify": "generate",
        "verify-only": "verify",
        "replay-eval": "animate",
    }
    return legacy_map[job.command]


def build_cli_tokens(job: EngineJob) -> list[str]:
    tokens = ["discoverex", _map_command_to_v2(job)]
    for key, value in job.args.items():
        _append_arg(tokens, key, value)
    for override in job.overrides:
        tokens.extend(["-o", override])
    return tokens


def build_worker_entrypoint(job: EngineJob) -> list[str]:
    cli = shlex.join(build_cli_tokens(job))
    return ["/bin/sh", "-lc", f'UV_CACHE_DIR="$PWD/.cache/uv" uv run {cli}']
