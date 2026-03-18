from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from delivery.spot_the_hidden.converter import build_game_bundle
from discoverex.artifact_paths import (
    composite_output_path,
    metadata_dir,
    output_manifest_path,
    outputs_dir,
    scene_json_path,
    verification_json_path,
)
from discoverex.domain.scene import Scene


@dataclass(frozen=True)
class OutputExportResult:
    manifest_path: Path
    lottie_path: Path
    layer_paths: list[Path]


def export_output_bundle(*, artifacts_root: Path, scene: Scene) -> OutputExportResult:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    out_dir = outputs_dir(artifacts_root, scene_id, version_id)
    layers_dir = out_dir / "layers"
    out_dir.mkdir(parents=True, exist_ok=True)
    layers_dir.mkdir(parents=True, exist_ok=True)

    exported_layers = _export_layers(scene=scene, layers_dir=layers_dir)
    lottie_path = out_dir / "animation.lottie"
    _write_lottie_bundle(
        scene=scene,
        lottie_path=lottie_path,
        exported_layers=exported_layers,
        artifacts_root=artifacts_root,
    )
    manifest_path = _write_output_manifest(
        scene=scene,
        artifacts_root=artifacts_root,
        exported_layers=exported_layers,
        lottie_path=lottie_path,
    )
    return OutputExportResult(
        manifest_path=manifest_path,
        lottie_path=lottie_path,
        layer_paths=exported_layers,
    )


def _export_layers(*, scene: Scene, layers_dir: Path) -> list[Path]:
    exported: list[Path] = []
    for layer in sorted(scene.layers.items, key=lambda item: item.order):
        source = Path(layer.image_ref)
        if not source.exists() or not source.is_file():
            continue
        suffix = source.suffix or ".png"
        target = layers_dir / f"{layer.order:03d}-{layer.layer_id}{suffix}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        exported.append(target)
    return exported


def _write_lottie_bundle(
    *,
    scene: Scene,
    lottie_path: Path,
    exported_layers: list[Path],
    artifacts_root: Path,
) -> None:
    animation_json = _build_lottie_animation(
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


def _build_lottie_animation(
    *,
    scene: Scene,
    exported_layers: list[Path],
    artifacts_root: Path,
) -> dict[str, object]:
    layer_lookup = {path.name.split("-", 1)[1].rsplit(".", 1)[0]: path for path in exported_layers}
    assets: list[dict[str, object]] = []
    layers: list[dict[str, object]] = []
    for index, layer in enumerate(sorted(scene.layers.items, key=lambda item: item.order), start=1):
        exported_path = layer_lookup.get(layer.layer_id)
        if exported_path is None:
            continue
        asset_id = f"image_{index}"
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
                "nm": layer.layer_id,
                "cl": layer.type.value,
                "refId": asset_id,
                "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "r": {"a": 0, "k": 0},
                    "p": {
                        "a": 0,
                        "k": [scene.background.width / 2, scene.background.height / 2, 0],
                    },
                    "a": {"a": 0, "k": [scene.background.width / 2, scene.background.height / 2, 0]},
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
            "scene_json": str(scene_json_path(artifacts_root, scene.meta.scene_id, scene.meta.version_id)),
        },
    }


def _write_output_manifest(
    *,
    scene: Scene,
    artifacts_root: Path,
    exported_layers: list[Path],
    lottie_path: Path,
) -> Path:
    scene_id = scene.meta.scene_id
    version_id = scene.meta.version_id
    manifest_path = output_manifest_path(artifacts_root, scene_id, version_id)
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
        "preview_image_path": composite_output_path(artifacts_root, scene_id, version_id).name,
        "scene_path": str(scene_json_path(artifacts_root, scene_id, version_id).relative_to(outputs_dir(artifacts_root, scene_id, version_id).parent)),
        "verification_path": str(
            verification_json_path(artifacts_root, scene_id, version_id).relative_to(
                outputs_dir(artifacts_root, scene_id, version_id).parent
            )
        ),
        "metadata_dir": str(metadata_dir(artifacts_root, scene_id, version_id).relative_to(outputs_dir(artifacts_root, scene_id, version_id).parent)),
        "layers": [
            {
                "layer_id": layer.layer_id,
                "type": layer.type.value,
                "path": f"layers/{path.name}",
                "source_region_id": layer.source_region_id,
            }
            for layer, path in zip(
                [item for item in sorted(scene.layers.items, key=lambda item: item.order) if Path(item.image_ref).exists()],
                exported_layers,
                strict=False,
            )
        ],
        "delivery_bundle": bundle.model_dump(mode="json"),
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest_path
