from __future__ import annotations

from pathlib import Path

from discoverex.domain.scene import Scene


class JsonSceneIOAdapter:
    def __init__(self, **_: str) -> None:
        pass

    def load_scene(self, scene_json: Path | str) -> Scene:
        path = Path(scene_json)
        return Scene.model_validate_json(path.read_text(encoding="utf-8"))

    def scene_json_path(self, scene: Scene, artifacts_root: Path) -> Path:
        return (
            artifacts_root
            / "scenes"
            / scene.meta.scene_id
            / scene.meta.version_id
            / "scene.json"
        )
