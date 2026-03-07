from __future__ import annotations

import shlex
from typing import Any

from discoverex.orchestrator_contract.schema import EngineJobV1


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


def build_cli_tokens(job: EngineJobV1) -> list[str]:
    tokens = ["discoverex", job.command]
    for key, value in job.args.items():
        _append_arg(tokens, key, value)
    for override in job.overrides:
        tokens.extend(["-o", override])
    return tokens


def build_worker_entrypoint(job: EngineJobV1) -> list[str]:
    cli = shlex.join(build_cli_tokens(job))
    return ["/bin/sh", "-lc", f'UV_CACHE_DIR="$PWD/.cache/uv" uv run {cli}']
