from __future__ import annotations

from pathlib import Path

from discoverex.application.context import AppContextLike
from discoverex.models.types import FxPrediction, FxRequest, ModelHandle

from .types import CompositeResolution


def resolve_composite_image_ref(
    *,
    background_asset_ref: str,
    fx_prediction: FxPrediction,
) -> CompositeResolution:
    for key in ("output_path", "image_ref", "composite_image_ref", "artifact_path"):
        value = fx_prediction.get(key)
        if not value:
            continue
        resolved = str(value)
        candidate_path = Path(resolved)
        if candidate_path.exists():
            return CompositeResolution(
                image_ref=str(candidate_path),
                artifact_path=candidate_path,
            )
        return CompositeResolution(image_ref=resolved, artifact_path=None)
    return CompositeResolution(image_ref=background_asset_ref, artifact_path=None)


def compose_scene(
    *,
    context: AppContextLike,
    background_asset_ref: str,
    scene_dir: Path,
    fx_handle: ModelHandle,
) -> CompositeResolution:
    fx_prediction = context.fx_model.predict(
        fx_handle,
        FxRequest(
            image_ref=background_asset_ref,
            mode="default",
            params={
                "output_path": str(scene_dir / "composite.png"),
                "width": int(context.runtime.width),
                "height": int(context.runtime.height),
                "prompt": "hidden object puzzle scene",
                "negative_prompt": "blurry, low quality, artifact",
                "seed": context.runtime.model_runtime.seed,
            },
        ),
    )
    return resolve_composite_image_ref(
        background_asset_ref=background_asset_ref,
        fx_prediction=fx_prediction,
    )
