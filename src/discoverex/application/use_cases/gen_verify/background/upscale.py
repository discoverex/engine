from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.application.context import AppContextLike
from discoverex.domain.scene import Background
from discoverex.models.types import FxRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from ..runtime_metrics import track_stage_vram
from .io import read_background_image_size

logger = get_logger("discoverex.generate.background")


def apply_background_canvas_upscale_if_needed(
    *,
    background: Background,
    context: AppContextLike,
    scene_dir: Path,
    upscaler_handle: ModelHandle,
    prompt: str,
    negative_prompt: str,
) -> Background:
    _ = (prompt, negative_prompt)
    factor = max(1, int(getattr(context.runtime, "background_upscale_factor", 1)))
    if factor <= 1:
        return background
    source_path = Path(background.asset_ref)
    if not source_path.exists():
        return background
    output_path = scene_dir / "assets" / "background" / "generated-background.canvas.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    emit_progress_event(
        stage="background_canvas_upscale",
        status="started",
        image_ref=background.asset_ref,
        output_path=str(output_path),
        factor=factor,
        width=int(background.width * factor),
        height=int(background.height * factor),
    )
    logger.info(
        "background canvas upscale started source=%s factor=%d size=%sx%s",
        background.asset_ref,
        factor,
        int(background.width * factor),
        int(background.height * factor),
    )
    started = perf_counter()
    with track_stage_vram(context, "background_canvas_upscale"):
        prediction = context.background_upscaler_model.predict(
            upscaler_handle,
            FxRequest(
                mode="canvas_upscale",
                image_ref=background.asset_ref,
                params={
                    "output_path": str(output_path),
                    "width": int(background.width * factor),
                    "height": int(background.height * factor),
                },
            ),
        )
    canvas_ref = str(prediction.get("output_path") or output_path)
    upscaled = read_background_image_size(image_path=Path(canvas_ref))
    background.metadata["base_background_ref"] = background.asset_ref
    background.metadata["background_upscale_factor"] = factor
    background.asset_ref = canvas_ref
    background.width = int(upscaled["width"])
    background.height = int(upscaled["height"])
    context.runtime.width = int(upscaled["width"])
    context.runtime.height = int(upscaled["height"])
    emit_progress_event(
        stage="background_canvas_upscale",
        status="completed",
        image_ref=background.asset_ref,
        factor=factor,
        width=background.width,
        height=background.height,
    )
    logger.info(
        "background canvas upscale completed output=%s duration=%s",
        background.asset_ref,
        format_seconds(started),
    )
    return background


def apply_background_detail_reconstruction_if_needed(
    *,
    background: Background,
    context: AppContextLike,
    scene_dir: Path,
    upscaler_handle: ModelHandle,
    prompt: str,
    negative_prompt: str,
    predictor_model: Any | None = None,
) -> Background:
    _ = (prompt, negative_prompt)
    factor = max(1, int(getattr(context.runtime, "background_upscale_factor", 1)))
    if factor <= 1:
        return background
    source_path = Path(background.asset_ref)
    if not source_path.exists():
        return background
    output_path = scene_dir / "assets" / "background" / "generated-background.hiresfix.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    emit_progress_event(
        stage="background_detail_reconstruction",
        status="started",
        image_ref=background.asset_ref,
        output_path=str(output_path),
        width=background.width,
        height=background.height,
    )
    logger.info(
        "background detail reconstruction started source=%s size=%sx%s",
        background.asset_ref,
        background.width,
        background.height,
    )
    started = perf_counter()
    model = predictor_model or context.background_upscaler_model
    with track_stage_vram(context, "background_detail_reconstruction"):
        prediction = model.predict(
            upscaler_handle,
            FxRequest(
                mode="detail_reconstruct",
                image_ref=background.asset_ref,
                params={
                    "output_path": str(output_path),
                    "width": int(background.width * factor),
                    "height": int(background.height * factor),
                },
            ),
        )
    refined_ref = str(prediction.get("output_path") or output_path)
    refined = read_background_image_size(image_path=Path(refined_ref))
    background.metadata["canvas_background_ref"] = background.asset_ref
    background.asset_ref = refined_ref
    background.width = int(refined["width"])
    background.height = int(refined["height"])
    context.runtime.width = int(refined["width"])
    context.runtime.height = int(refined["height"])
    emit_progress_event(
        stage="background_detail_reconstruction",
        status="completed",
        image_ref=background.asset_ref,
        width=background.width,
        height=background.height,
    )
    logger.info(
        "background detail reconstruction completed output=%s duration=%s",
        background.asset_ref,
        format_seconds(started),
    )
    return background


def apply_background_hires_fix_if_needed(
    *,
    background: Background,
    context: AppContextLike,
    scene_dir: Path,
    upscaler_handle: ModelHandle,
    prompt: str,
    negative_prompt: str,
    predictor_model: Any | None = None,
) -> Background:
    return apply_background_detail_reconstruction_if_needed(
        background=background,
        context=context,
        scene_dir=scene_dir,
        upscaler_handle=upscaler_handle,
        prompt=prompt,
        negative_prompt=negative_prompt,
        predictor_model=predictor_model,
    )
