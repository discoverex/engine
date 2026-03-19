from __future__ import annotations

from pathlib import Path

from discoverex.artifact_paths import outputs_dir
from discoverex.domain.scene import Scene

from .layers import export_layers
from .render import write_lottie_bundle, write_output_manifest
from .shared import candidate_by_region
from .types import OutputExportResult


def export_output_bundle(*, artifacts_root: Path, scene: Scene) -> OutputExportResult:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    out_dir = outputs_dir(artifacts_root, scene_id, version_id)
    layers_dir = out_dir / "layers" / "objects"
    source_layers_dir = out_dir / "layers" / "source-objects"
    out_dir.mkdir(parents=True, exist_ok=True)
    layers_dir.mkdir(parents=True, exist_ok=True)
    source_layers_dir.mkdir(parents=True, exist_ok=True)

    candidates = candidate_by_region(scene)
    exported_layers, source_layer_paths = export_layers(
        scene=scene,
        layers_dir=layers_dir,
        source_layers_dir=source_layers_dir,
        candidates=candidates,
    )
    lottie_path = out_dir / "animation.lottie"
    write_lottie_bundle(
        scene=scene,
        lottie_path=lottie_path,
        exported_layers=exported_layers,
        artifacts_root=artifacts_root,
    )
    manifest_path = write_output_manifest(
        scene=scene,
        artifacts_root=artifacts_root,
        exported_layers=exported_layers,
        source_layer_paths=source_layer_paths,
        lottie_path=lottie_path,
    )
    return OutputExportResult(
        manifest_path=manifest_path,
        lottie_path=lottie_path,
        layer_paths=exported_layers,
        source_layer_paths=source_layer_paths,
    )
