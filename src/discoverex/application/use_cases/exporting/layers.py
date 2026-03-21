from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from discoverex.domain.scene import LayerItem, Scene

from .types import CandidateLayerPayload


def export_layers(
    *,
    scene: Scene,
    layers_dir: Path,
    source_layers_dir: Path,
    candidates: dict[str, CandidateLayerPayload],
) -> tuple[list[Path], list[Path]]:
    exported: list[Path] = []
    source_layers: list[Path] = []
    for layer in sorted(scene.layers.items, key=lambda item: item.order):
        if layer.source_region_id and layer.source_region_id in candidates:
            candidate = candidates[layer.source_region_id]
            full_canvas = render_full_canvas_object_layer(
                scene=scene,
                layer=layer,
                candidate=candidate,
                layers_dir=layers_dir,
            )
            if full_canvas is not None:
                exported.append(full_canvas)
            source_layer = export_source_object_layer(
                layer=layer,
                candidate=candidate,
                source_layers_dir=source_layers_dir,
            )
            if source_layer is not None:
                source_layers.append(source_layer)
            continue

        source = Path(layer.image_ref)
        if not source.exists() or not source.is_file():
            continue
        suffix = source.suffix or ".png"
        target = layers_dir / f"{layer.order:03d}-{layer.layer_id}{suffix}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        exported.append(target)
    return exported, source_layers


def render_full_canvas_object_layer(
    *,
    scene: Scene,
    layer: LayerItem,
    candidate: CandidateLayerPayload,
    layers_dir: Path,
) -> Path | None:
    source_ref = candidate.get("layer_image_ref") or candidate.get("object_image_ref")
    if not isinstance(source_ref, str):
        return None
    source_path = Path(source_ref)
    if not source_path.exists() or not source_path.is_file() or layer.bbox is None:
        return None
    target = layers_dir / f"{layer.order:03d}-{layer.layer_id}.png"
    with Image.open(source_path).convert("RGBA") as object_image:
        canvas = Image.new(
            "RGBA",
            (int(scene.background.width), int(scene.background.height)),
            color=(0, 0, 0, 0),
        )
        resized = object_image.resize(
            (
                max(1, int(round(layer.bbox.w))),
                max(1, int(round(layer.bbox.h))),
            ),
            Image.Resampling.LANCZOS,
        )
        canvas.paste(
            resized,
            (int(round(layer.bbox.x)), int(round(layer.bbox.y))),
            resized,
        )
        canvas.save(target)
    return target


def export_source_object_layer(
    *,
    layer: LayerItem,
    candidate: CandidateLayerPayload,
    source_layers_dir: Path,
) -> Path | None:
    source_ref = (
        candidate.get("layer_image_ref")
        or candidate.get("object_image_ref")
        or candidate.get("candidate_image_ref")
    )
    if not isinstance(source_ref, str):
        return None
    source_path = Path(source_ref)
    if not source_path.exists() or not source_path.is_file():
        return None
    target = source_layers_dir / f"{layer.order:03d}-{layer.layer_id}{source_path.suffix or '.png'}"
    if source_path.resolve() != target.resolve():
        shutil.copy2(source_path, target)
    return target
