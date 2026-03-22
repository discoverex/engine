from __future__ import annotations

from pathlib import Path
import shutil

from discoverex.artifact_paths import outputs_dir
from discoverex.domain.scene import Scene

from .intermediates import export_originals
from .layers import export_layers
from .render import write_lottie_bundle, write_output_manifest
from .shared import candidate_by_region
from .types import OutputExportResult


def _copy_tree(*, source: Path, target: Path) -> Path | None:
    if not source.exists() or not source.is_dir():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def _build_delivery_bundle(
    *,
    artifacts_root: Path,
    scene: Scene,
    layers_root_dir: Path,
) -> list[Path]:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    scene_root = outputs_dir(artifacts_root, scene_id, version_id).parent
    delivery_root = outputs_dir(artifacts_root, scene_id, version_id) / "delivery"
    copied_roots: list[Path] = []
    metadata_copy = _copy_tree(
        source=scene_root / "metadata",
        target=delivery_root / "metadata",
    )
    if metadata_copy is not None:
        copied_roots.append(metadata_copy)
    layers_copy = _copy_tree(
        source=layers_root_dir,
        target=delivery_root / "layers",
    )
    if layers_copy is not None:
        copied_roots.append(layers_copy)
    copied_files: list[Path] = []
    for root in copied_roots:
        copied_files.extend(sorted(path for path in root.rglob("*") if path.is_file()))
    return copied_files


def export_output_bundle(*, artifacts_root: Path, scene: Scene) -> OutputExportResult:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    out_dir = outputs_dir(artifacts_root, scene_id, version_id)
    layers_root_dir = out_dir / "layers"
    layers_dir = out_dir / "layers" / "objects"
    source_layers_dir = out_dir / "layers" / "source-objects"
    originals_dir = out_dir / "original"
    out_dir.mkdir(parents=True, exist_ok=True)
    layers_root_dir.mkdir(parents=True, exist_ok=True)
    layers_dir.mkdir(parents=True, exist_ok=True)
    source_layers_dir.mkdir(parents=True, exist_ok=True)
    originals_dir.mkdir(parents=True, exist_ok=True)

    candidates = candidate_by_region(scene)
    exported_layers, source_layer_paths = export_layers(
        scene=scene,
        layers_dir=layers_dir,
        source_layers_dir=source_layers_dir,
        candidates=candidates,
    )
    original_paths, original_entries = export_originals(
        originals_dir=originals_dir,
        candidates=candidates,
    )
    lottie_path = layers_root_dir / "animation.lottie"
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
        original_entries=original_entries,
        lottie_path=lottie_path,
    )
    delivery_paths = _build_delivery_bundle(
        artifacts_root=artifacts_root,
        scene=scene,
        layers_root_dir=layers_root_dir,
    )
    return OutputExportResult(
        manifest_path=manifest_path,
        lottie_path=lottie_path,
        layer_paths=exported_layers,
        source_layer_paths=source_layer_paths,
        original_paths=original_paths,
        delivery_paths=delivery_paths,
    )
