from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "EngineRunSpec",
    "EngineRunSpecV1",
    "EngineRunSpecV2",
    "JobSpec",
    "EngineJob",
    "EngineJobV1",
    "EngineJobV2",
    "JobRuntime",
    "OrchestratorInputs",
    "OrchestratorInputsV1",
    "OrchestratorInputsV2",
    "build_cli_tokens",
    "build_worker_entrypoint",
    "is_legacy_command",
    "run_orchestrator_job",
]


def __getattr__(name: str) -> Any:
    if name == "run_orchestrator_job":
        return import_module(
            "discoverex.orchestrator_contract.launcher"
        ).run_orchestrator_job
    if name in {"build_cli_tokens", "build_worker_entrypoint", "is_legacy_command"}:
        module = import_module("discoverex.orchestrator_contract.runner")
        return getattr(module, name)
    if name in {
        "EngineRunSpec",
        "EngineRunSpecV1",
        "EngineRunSpecV2",
        "JobSpec",
        "EngineJob",
        "EngineJobV1",
        "EngineJobV2",
        "JobRuntime",
        "OrchestratorInputs",
        "OrchestratorInputsV1",
        "OrchestratorInputsV2",
    }:
        module = import_module("discoverex.orchestrator_contract.schema")
        return getattr(module, name)
    raise AttributeError(name)
