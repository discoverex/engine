from __future__ import annotations

from typing import Any, TypedDict


class RuntimeConfig(TypedDict, total=False):
    mode: str
    bootstrap_mode: str
    extras: list[str]
    extra_env: dict[str, str]


class JobSpecInputs(TypedDict, total=False):
    contract_version: str
    command: str
    config_name: str
    config_dir: str
    args: dict[str, Any]
    overrides: list[str]
    runtime: RuntimeConfig


class JobSpec(TypedDict, total=False):
    run_mode: str
    engine: str
    repo_url: str | None
    ref: str | None
    entrypoint: list[str]
    config: Any | None  # Placeholder for explicit config if needed
    inputs: JobSpecInputs
    env: dict[str, str]
    outputs_prefix: str | None
    job_name: str | None
