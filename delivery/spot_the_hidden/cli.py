from __future__ import annotations

import argparse
from pathlib import Path

from .converter import build_game_bundle
from .io import convert_scene_json_to_bundle, load_scene


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spot-the-hidden delivery bundle builder")
    parser.add_argument("--scene-json", required=True, help="Path to source scene.json")
    parser.add_argument("--output", default=None, help="Output bundle path")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate transform without writing output",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    scene_path = Path(args.scene_json)
    scene = load_scene(scene_path)
    bundle = build_game_bundle(scene=scene, source_scene_json=str(scene_path))
    if args.validate_only:
        print(bundle.model_dump_json(indent=2))
        return
    output = convert_scene_json_to_bundle(scene_json_path=scene_path, output_path=args.output)
    print(str(output))


if __name__ == "__main__":
    main()
