from __future__ import annotations

import json
from pathlib import Path

from discoverex.domain.scene import Scene

from .converter import build_game_bundle
from .schema import GameBundle


def default_bundle_path(scene_json_path: Path | str) -> Path:
    scene_path = Path(scene_json_path)
    return scene_path.parent / "delivery" / "spot_hidden_bundle.json"


def load_scene(scene_json_path: Path | str) -> Scene:
    path = Path(scene_json_path)
    return Scene.model_validate_json(path.read_text(encoding="utf-8"))


def write_bundle(bundle: GameBundle, output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def convert_scene_json_to_bundle(
    scene_json_path: Path | str,
    output_path: Path | str | None = None,
) -> Path:
    scene_path = Path(scene_json_path)
    scene = load_scene(scene_path)
    bundle = build_game_bundle(scene=scene, source_scene_json=str(scene_path))
    target = Path(output_path) if output_path is not None else default_bundle_path(scene_path)
    return write_bundle(bundle, target)
