from __future__ import annotations

from typing import TypedDict
from dataclasses import dataclass


class OutputUploadMap(TypedDict, total=False):
    stdout: str
    stderr: str
    result: str
    manifest: str


@dataclass(frozen=True)
class EngineUploadResult:
    artifact_uris: dict[str, str]
    manifest_uri: str
    mlflow_tags: dict[str, str]
