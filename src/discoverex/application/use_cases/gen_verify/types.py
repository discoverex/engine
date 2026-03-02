from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RunIds:
    scene_id: str
    version_id: str
    pipeline_run_id: str


@dataclass(frozen=True, slots=True)
class CompositeResolution:
    image_ref: str
    artifact_path: Path | None
