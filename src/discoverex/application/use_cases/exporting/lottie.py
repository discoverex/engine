from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from discoverex.artifact_paths import scene_json_path
from discoverex.domain.scene import Scene

from .shared import (
    build_object_entries,
    candidate_by_region,
    lottie_layer_name,
    object_entry_by_region,
)


def write_lottie_bundle(
    *,
    scene: Scene,
    lottie_path: Path,
    exported_layers: list[Path],
    artifacts_root: Path,
) -> None:
    animation_json = build_lottie_animation(
        scene=scene,
        exported_layers=exported_layers,
        artifacts_root=artifacts_root,
    )
    bundle_manifest = {
        "version": "2.0",
        "generator": "discoverex",
        "animations": [{"id": "scene", "path": "animations/scene.json"}],
    }
    with ZipFile(lottie_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(bundle_manifest, ensure_ascii=True, indent=2),
        )
        archive.writestr(
            "animations/scene.json",
            json.dumps(animation_json, ensure_ascii=False, indent=2),
        )
        for layer_path in exported_layers:
            archive.write(layer_path, arcname=f"images/{layer_path.name}")


def build_lottie_animation(
    *,
    scene: Scene,
    exported_layers: list[Path],
    artifacts_root: Path,
) -> dict[str, object]:
    layer_lookup = {
        path.name.split("-", 1)[1].rsplit(".", 1)[0]: path for path in exported_layers
    }
    candidates = candidate_by_region(scene)
    object_entries = build_object_entries(scene=scene, candidates=candidates)
    entries_by_region = object_entry_by_region(object_entries)
    assets: list[dict[str, object]] = []
    layers: list[dict[str, object]] = []
    for index, layer in enumerate(
        sorted(scene.layers.items, key=lambda item: item.order), start=1
    ):
        exported_path = layer_lookup.get(layer.layer_id)
        if exported_path is None:
            continue
        asset_id = f"image_{index}"
        entry = (
            entries_by_region.get(layer.source_region_id)
            if layer.source_region_id is not None
            else None
        )
        assets.append(
            {
                "id": asset_id,
                "w": scene.background.width,
                "h": scene.background.height,
                "u": "images/",
                "p": exported_path.name,
                "e": 0,
            }
        )
        layers.append(
            {
                "ddd": 0,
                "ind": index,
                "ty": 2,
                "nm": lottie_layer_name(layer=layer, object_entry=entry),
                "cl": layer.type.value,
                "refId": asset_id,
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 0,
                        "k": [
                            scene.background.width / 2,
                            scene.background.height / 2,
                            0,
                        ],
                    },
                    "a": {
                        "a": 0,
                        "k": [
                            scene.background.width / 2,
                            scene.background.height / 2,
                            0,
                        ],
                    },
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "ao": 0,
                "ip": 0,
                "op": 60,
                "st": 0,
                "bm": 0,
            }
        )
    return {
        "v": "5.12.2",
        "fr": 60,
        "ip": 0,
        "op": 60,
        "w": scene.background.width,
        "h": scene.background.height,
        "nm": f"{scene.meta.scene_id}:{scene.meta.version_id}",
        "ddd": 0,
        "assets": assets,
        "layers": layers,
        "markers": [],
        "metadata": {
            "scene_id": scene.meta.scene_id,
            "version_id": scene.meta.version_id,
            "scene_json": str(
                scene_json_path(
                    artifacts_root, scene.meta.scene_id, scene.meta.version_id
                )
            ),
            "object_entries": object_entries,
        },
    }
