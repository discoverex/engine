from __future__ import annotations

from pathlib import Path
from typing import Protocol

from discoverex.domain.scene import Scene


class ArtifactStorePort(Protocol):
    def save_scene_bundle(self, scene: Scene) -> Path: ...


class MetadataStorePort(Protocol):
    def upsert_scene_metadata(self, scene: Scene) -> None: ...
