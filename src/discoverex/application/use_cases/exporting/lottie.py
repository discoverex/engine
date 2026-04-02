from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

from discoverex.domain.scene import Scene

from .shared import bbox_center
from .types import ObjectRenderSpec


def write_object_lottie_bundles(
    *,
    scene: Scene,
    specs: list[ObjectRenderSpec],
    object_png_paths: list[Path],
    lottie_dir: Path,
) -> list[Path]:
    lottie_dir.mkdir(parents=True, exist_ok=True)
    png_by_object = {path.stem: path for path in object_png_paths}
    exported: list[Path] = []
    for spec in specs:
        png_path = png_by_object.get(spec.object_id)
        if png_path is None:
            continue
        target = lottie_dir / f"{spec.object_id}.lottie"
        animation_json = build_object_lottie_animation(
            scene=scene,
            spec=spec,
            object_png_path=png_path,
        )
        with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "version": "2.0",
                        "generator": "discoverex",
                        "animations": [{"id": spec.object_id, "path": f"animations/{spec.object_id}.json"}],
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
            )
            archive.writestr(
                f"animations/{spec.object_id}.json",
                json.dumps(animation_json, ensure_ascii=False, indent=2),
            )
            archive.write(png_path, arcname=f"images/{png_path.name}")
        exported.append(target)
    return exported


def build_object_lottie_animation(
    *,
    scene: Scene,
    spec: ObjectRenderSpec,
    object_png_path: Path,
) -> dict[str, object]:
    with Image.open(object_png_path).convert("RGBA") as object_image:
        asset_width = max(1, int(object_image.width))
        asset_height = max(1, int(object_image.height))
    center_x, center_y = bbox_center(spec.bbox)
    scale_x = (spec.bbox["w"] / asset_width) * 100.0
    scale_y = (spec.bbox["h"] / asset_height) * 100.0
    return {
        "v": "5.12.2",
        "fr": 60,
        "ip": 0,
        "op": 60,
        "w": int(scene.background.width),
        "h": int(scene.background.height),
        "nm": spec.object_id,
        "ddd": 0,
        "assets": [
            {
                "id": spec.lottie_id,
                "w": asset_width,
                "h": asset_height,
                "u": "images/",
                "p": object_png_path.name,
                "e": 0,
            }
        ],
        "layers": [
            {
                "ddd": 0,
                "ind": 1,
                "ty": 2,
                "nm": spec.name,
                "refId": spec.lottie_id,
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [center_x, center_y, 0]},
                    "a": {"a": 0, "k": [asset_width / 2.0, asset_height / 2.0, 0]},
                    "s": {"a": 0, "k": [scale_x, scale_y, 100]},
                },
                "ao": 0,
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0,
            }
        ],
        "markers": [],
        "metadata": {
            "scene_id": scene.meta.scene_id,
            "version_id": scene.meta.version_id,
            "region_id": spec.region_id,
            "bbox": spec.bbox,
            "prompt": spec.prompt,
            "order": spec.order,
        },
    }
