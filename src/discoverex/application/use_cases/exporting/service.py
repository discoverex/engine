from __future__ import annotations

from pathlib import Path
import shutil

from discoverex.adapters.outbound.io.json_files import write_json_file
from discoverex.artifact_paths import outputs_dir
from discoverex.domain.scene import Scene

from .intermediates import export_originals
from .layers import export_background, export_object_images
from .lottie import write_object_lottie_bundles
from .manifest import write_output_manifest
from .shared import build_object_specs, candidate_by_region
from .types import ObjectRenderSpec, OutputExportResult


def _copy_tree(*, source: Path, target: Path) -> list[Path]:
    if not source.exists() or not source.is_dir():
        return []
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=True)
    return sorted(path for path in target.rglob("*") if path.is_file())


def _copy_file(*, source: Path, target: Path) -> Path | None:
    if not source.exists() or not source.is_file():
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def _build_delivery_bundle(
    *,
    artifacts_root: Path,
    scene: Scene,
    background_path: Path,
    object_png_paths: list[Path],
    object_lottie_paths: list[Path],
    delivery_manifest_path: Path,
) -> list[Path]:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    scene_root = outputs_dir(artifacts_root, scene_id, version_id).parent
    delivery_root = outputs_dir(artifacts_root, scene_id, version_id) / "delivery"
    copied: list[Path] = []
    copied.extend(
        _copy_tree(
            source=scene_root / "metadata",
            target=delivery_root / "metadata",
        )
    )
    for source, relative in (
        (background_path, Path("background") / background_path.name),
        (delivery_manifest_path, delivery_manifest_path.name),
    ):
        target = _copy_file(source=source, target=delivery_root / relative)
        if target is not None:
            copied.append(target)
    for path in object_png_paths:
        target = _copy_file(source=path, target=delivery_root / "objects" / path.name)
        if target is not None:
            copied.append(target)
    for path in object_lottie_paths:
        target = _copy_file(source=path, target=delivery_root / "objects" / path.name)
        if target is not None:
            copied.append(target)
    return copied


def _write_delivery_manifest(
    *,
    artifacts_root: Path,
    scene: Scene,
    background_path: Path,
    object_png_paths: list[Path],
    object_specs: list[ObjectRenderSpec],
) -> Path:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    out_dir = outputs_dir(artifacts_root, scene_id, version_id)
    delivery_dir = out_dir / "delivery"
    png_by_object = {path.stem: path for path in object_png_paths}
    payload = {
        "scene_ref": {
            "title": str(scene.background.metadata.get("name") or scene_id),
            "scene_id": scene_id,
            "version_id": version_id,
        },
        "background_img": {
            "image_id": "background",
            "src": (Path("background") / background_path.name).as_posix(),
            "prompt": str(scene.background.metadata.get("prompt") or ""),
            "width": int(scene.background.width),
            "height": int(scene.background.height),
        },
        "answers": [
            {
                "lottie_id": spec.lottie_id,
                "name": spec.name,
                "title": spec.title,
                "src": (Path("objects") / png_by_object[spec.object_id].name).as_posix(),
                "bbox": spec.bbox,
                "prompt": spec.prompt,
                "order": spec.order,
            }
            for spec in object_specs
            if spec.object_id in png_by_object
        ],
    }
    manifest_path = delivery_dir / "manifest.json"
    return write_json_file(manifest_path, payload)


def export_output_bundle(*, artifacts_root: Path, scene: Scene) -> OutputExportResult:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    out_dir = outputs_dir(artifacts_root, scene_id, version_id)
    background_dir = out_dir / "background"
    objects_dir = out_dir / "objects"
    originals_dir = out_dir / "original"
    out_dir.mkdir(parents=True, exist_ok=True)
    background_dir.mkdir(parents=True, exist_ok=True)
    objects_dir.mkdir(parents=True, exist_ok=True)
    originals_dir.mkdir(parents=True, exist_ok=True)

    candidates = candidate_by_region(scene)
    object_specs = build_object_specs(scene=scene, candidates=candidates)
    background_path = export_background(
        background_ref=scene.background.asset_ref,
        background_dir=background_dir,
    )
    object_png_paths = export_object_images(specs=object_specs, objects_dir=objects_dir)
    object_lottie_paths = write_object_lottie_bundles(
        scene=scene,
        specs=object_specs,
        object_png_paths=object_png_paths,
        lottie_dir=objects_dir,
    )
    original_paths, original_entries = export_originals(
        originals_dir=originals_dir,
        candidates=candidates,
    )
    manifest_path = write_output_manifest(
        scene=scene,
        artifacts_root=artifacts_root,
        background_path=background_path,
        object_png_paths=object_png_paths,
        original_entries=original_entries,
        object_specs=object_specs,
    )
    delivery_manifest_path = _write_delivery_manifest(
        artifacts_root=artifacts_root,
        scene=scene,
        background_path=background_path,
        object_png_paths=object_png_paths,
        object_specs=object_specs,
    )
    delivery_paths = _build_delivery_bundle(
        artifacts_root=artifacts_root,
        scene=scene,
        background_path=background_path,
        object_png_paths=object_png_paths,
        object_lottie_paths=object_lottie_paths,
        delivery_manifest_path=delivery_manifest_path,
    )
    return OutputExportResult(
        manifest_path=manifest_path,
        delivery_manifest_path=delivery_manifest_path,
        background_path=background_path,
        object_png_paths=object_png_paths,
        object_lottie_paths=object_lottie_paths,
        original_paths=original_paths,
        delivery_paths=delivery_paths,
    )
