from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

ARTIFACT_DIR_ENV = "ORCH_ENGINE_ARTIFACT_DIR"
ARTIFACT_MANIFEST_ENV = "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"


class EngineArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_name: str
    relative_path: str
    content_type: str | None = None
    mlflow_tag: str | None = None
    description: str | None = None


class EngineArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    artifacts: list[EngineArtifact]


def artifact_root_from_env() -> Path:
    raw = os.getenv(ARTIFACT_DIR_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"missing required env: {ARTIFACT_DIR_ENV}")
    return Path(raw).resolve()


def manifest_path_from_env() -> Path:
    raw = os.getenv(ARTIFACT_MANIFEST_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"missing required env: {ARTIFACT_MANIFEST_ENV}")
    return Path(raw).resolve()


def write_engine_artifact_manifest(
    artifacts: list[EngineArtifact | dict[str, str | None]],
) -> Path | None:
    if not artifacts:
        return None
    root = artifact_root_from_env()
    manifest_path = manifest_path_from_env()
    entries = [EngineArtifact.model_validate(item) for item in artifacts]
    for entry in entries:
        artifact_path = _validate_relative_path(root, entry.relative_path)
        if not artifact_path.exists():
            raise RuntimeError(f"artifact file does not exist: {entry.relative_path}")
    manifest = EngineArtifactManifest(artifacts=entries)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="python"), ensure_ascii=True, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _validate_relative_path(root: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise RuntimeError("artifact relative_path must not be absolute")
    if ".." in candidate.parts:
        raise RuntimeError("artifact relative_path must stay under artifact root")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            "artifact relative_path must stay under artifact root"
        ) from exc
    return resolved


__all__ = [
    "ARTIFACT_DIR_ENV",
    "ARTIFACT_MANIFEST_ENV",
    "EngineArtifact",
    "EngineArtifactManifest",
    "artifact_root_from_env",
    "manifest_path_from_env",
    "write_engine_artifact_manifest",
]
