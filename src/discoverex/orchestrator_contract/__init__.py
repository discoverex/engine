from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "ARTIFACT_DIR_ENV",
    "ARTIFACT_MANIFEST_ENV",
    "EngineRunSpec",
    "EngineRunSpecV1",
    "EngineRunSpecV2",
    "EngineArtifact",
    "EngineArtifactManifest",
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
    "write_engine_artifact_manifest",
    "run_orchestrator_job",
]


def __getattr__(name: str) -> Any:
    if name == "run_orchestrator_job":
        return import_module(
            "discoverex.orchestrator_contract.launcher"
        ).run_orchestrator_job
    if name in {"build_cli_tokens", "build_worker_entrypoint", "is_legacy_command"}:
        module = import_module("discoverex.application.contracts.execution")
        return getattr(module, name)
    if name in {
        "ARTIFACT_DIR_ENV",
        "ARTIFACT_MANIFEST_ENV",
        "EngineArtifact",
        "EngineArtifactManifest",
        "write_engine_artifact_manifest",
    }:
        module = import_module("discoverex.orchestrator_contract.artifacts")
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
        module = import_module("discoverex.application.contracts.execution")
        return getattr(module, name)
    raise AttributeError(name)
