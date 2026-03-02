from __future__ import annotations

from pathlib import Path
from typing import Protocol

from discoverex.domain.scene import Scene


class SceneIOPort(Protocol):
    def load_scene(self, scene_json: Path | str) -> Scene: ...

    def scene_json_path(self, scene: Scene, artifacts_root: Path) -> Path: ...
