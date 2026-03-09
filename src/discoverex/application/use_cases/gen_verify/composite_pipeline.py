from __future__ import annotations

from pathlib import Path
from time import perf_counter

from discoverex.application.context import AppContextLike
from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .types import CompositeResolution

logger = get_logger("discoverex.generate.final_render")


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
    prompt: str = "hidden object puzzle scene",
    negative_prompt: str = "blurry, low quality, artifact",
) -> CompositeResolution:
    started = perf_counter()
    output_path = scene_dir / "composite.png"
    logger.info(
        "final render started source=%s output=%s size=%sx%s",
        background_asset_ref,
        output_path,
        int(context.runtime.width),
        int(context.runtime.height),
    )
    fx_prediction = context.fx_model.predict(
        fx_handle,
        FxRequest(
            image_ref=background_asset_ref,
            mode="default",
            params={
                "output_path": str(output_path),
                "width": int(context.runtime.width),
                "height": int(context.runtime.height),
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "seed": context.runtime.model_runtime.seed,
            },
        ),
    )
    resolved = resolve_composite_image_ref(
        background_asset_ref=background_asset_ref,
        fx_prediction=fx_prediction,
    )
    logger.info(
        "final render completed output=%s duration=%s",
        resolved.image_ref,
        format_seconds(started),
    )
    return resolved
