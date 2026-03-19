from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineUploadResult:
    artifact_uris: dict[str, str]
    manifest_uri: str
