from __future__ import annotations

from pathlib import Path

from discoverex.adapters.outbound.io.json_files import write_json_file
from discoverex.artifact_paths import output_manifest_path
from discoverex.domain.scene import Scene

from .shared import file_name
from .types import ObjectRenderSpec, OriginalAssetEntry


def write_output_manifest(
    *,
    scene: Scene,
    artifacts_root: Path,
    background_path: Path,
    object_png_paths: list[Path],
    original_entries: list[OriginalAssetEntry],
    object_specs: list[ObjectRenderSpec],
) -> Path:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    manifest_path = output_manifest_path(artifacts_root, scene_id, version_id)
    png_by_object = {path.stem: path for path in object_png_paths}
    payload = {
        "scene_ref": {
            "title": str(scene.background.metadata.get("name") or scene.meta.scene_id),
            "scene_id": scene_id,
            "version_id": version_id,
        },
        "background_img": {
            "image_id": "background",
            "src": file_name(background_path),
            "prompt": str(scene.background.metadata.get("prompt") or ""),
            "width": int(scene.background.width),
            "height": int(scene.background.height),
        },
        "answers": [
            {
                "lottie_id": spec.lottie_id,
                "name": spec.name,
                "title": spec.title,
                "src": file_name(png_by_object[spec.object_id]),
                "bbox": spec.bbox,
                "prompt": spec.prompt,
                "order": spec.order,
            }
            for spec in object_specs
            if spec.object_id in png_by_object
        ],
        "original": original_entries,
    }
    return write_json_file(manifest_path, payload)
