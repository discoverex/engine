from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.adapters.outbound.io.json_files import write_json_file
from discoverex.artifact_paths import (
    composite_output_path,
    metadata_dir,
    output_manifest_path,
    outputs_dir,
    scene_json_path,
    verification_json_path,
)
from discoverex.domain.scene import Scene

from .shared import (
    build_object_entries,
    build_object_source_entries,
    candidate_by_region,
    object_entry_by_region,
)
from .types import OriginalAssetEntry, ObjectEntry


def write_output_manifest(
    *,
    scene: Scene,
    artifacts_root: Path,
    exported_layers: list[Path],
    source_layer_paths: list[Path],
    original_entries: list[OriginalAssetEntry],
    lottie_path: Path,
) -> Path:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    manifest_path = output_manifest_path(artifacts_root, scene_id, version_id)
    candidates = candidate_by_region(scene)
    object_entries = build_object_entries(scene=scene, candidates=candidates)
    entries_by_region = object_entry_by_region(object_entries)
    from delivery.spot_the_hidden.converter import build_game_bundle

    bundle = build_game_bundle(
        scene=scene,
        source_scene_json=str(scene_json_path(artifacts_root, scene_id, version_id)),
    )
    payload = {
        "scene_id": scene_id,
        "version_id": version_id,
        "pipeline_run_id": scene.meta.pipeline_run_id,
        "status": scene.meta.status.value,
        "created_at": scene.meta.created_at.isoformat(),
        "updated_at": scene.meta.updated_at.isoformat(),
        "lottie_path": lottie_path.name,
        "preview_image_path": composite_output_path(
            artifacts_root, scene_id, version_id
        ).name,
        "scene_path": str(
            scene_json_path(artifacts_root, scene_id, version_id).relative_to(
                outputs_dir(artifacts_root, scene_id, version_id).parent
            )
        ),
        "verification_path": str(
            verification_json_path(artifacts_root, scene_id, version_id).relative_to(
                outputs_dir(artifacts_root, scene_id, version_id).parent
            )
        ),
        "metadata_dir": str(
            metadata_dir(artifacts_root, scene_id, version_id).relative_to(
                outputs_dir(artifacts_root, scene_id, version_id).parent
            )
        ),
        "layers": build_layer_manifest(
            scene=scene,
            exported_layers=exported_layers,
            entries_by_region=entries_by_region,
        ),
        "source_layers": [
            {"path": f"layers/source-objects/{path.name}"}
            for path in source_layer_paths
        ],
        "original": original_entries,
        "object_entries": object_entries,
        "object_sources": build_object_source_entries(
            candidates=candidates,
            entries_by_region=entries_by_region,
        ),
        "delivery_bundle": bundle.model_dump(mode="json"),
    }
    return write_json_file(manifest_path, payload)


def build_layer_manifest(
    *,
    scene: Scene,
    exported_layers: list[Path],
    entries_by_region: dict[str, ObjectEntry],
) -> list[dict[str, Any]]:
    visible_layers = [
        item
        for item in sorted(scene.layers.items, key=lambda item: item.order)
        if Path(item.image_ref).exists()
    ]
    manifest: list[dict[str, Any]] = []
    for layer, path in zip(visible_layers, exported_layers, strict=False):
        region_entry = (
            entries_by_region.get(layer.source_region_id)
            if layer.source_region_id is not None
            else None
        )
        manifest.append(
            {
                "layer_id": layer.layer_id,
                "type": layer.type.value,
                "path": f"layers/objects/{path.name}",
                "source_region_id": layer.source_region_id,
                "object_number": region_entry["object_number"] if region_entry else None,
                "center": region_entry["center"] if region_entry else None,
                "description": (
                    "aligned object render with alpha" if region_entry else None
                ),
            }
        )
    return manifest
