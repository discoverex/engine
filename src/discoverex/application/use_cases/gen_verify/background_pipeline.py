from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.application.context import AppContextLike
from discoverex.domain.scene import Background
from discoverex.models.types import FxRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from .composite_pipeline import resolve_composite_image_ref
from .runtime_metrics import track_stage_vram
from .scene_builder import build_background
from .types import PromptStageRecord

_DEFAULT_BACKGROUND_NEGATIVE = "blurry, low quality, artifact"
logger = get_logger("discoverex.generate.background")


def build_background_from_inputs(
    *,
    context: AppContextLike,
    scene_dir: Path,
    fx_handle: ModelHandle,
    background_asset_ref: str | None,
    background_prompt: str | None,
    background_negative_prompt: str | None,
) -> tuple[Background, PromptStageRecord]:
    prompt = (background_prompt or "").strip()
    negative_prompt = (background_negative_prompt or "").strip()

    if prompt:
        started = perf_counter()
        output_path = (
            scene_dir / "assets" / "background" / "generated-background.png"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        emit_progress_event(
            stage="background_generation",
            status="started",
            mode="prompt",
            output_path=str(output_path),
            width=int(context.runtime.width),
            height=int(context.runtime.height),
        )
        logger.info(
            "background generation started mode=prompt output=%s size=%sx%s",
            output_path,
            int(context.runtime.width),
            int(context.runtime.height),
        )
        with track_stage_vram(context, "background_generation"):
            prediction = context.background_generator_model.predict(
                fx_handle,
                FxRequest(
                    mode="background",
                    params={
                        "output_path": str(output_path),
                        "width": int(context.runtime.width),
                        "height": int(context.runtime.height),
                        "prompt": prompt,
                        "negative_prompt": negative_prompt or _DEFAULT_BACKGROUND_NEGATIVE,
                        "seed": context.runtime.model_runtime.seed,
                    },
                ),
            )
        fallback_ref = (background_asset_ref or "").strip()
        resolved = resolve_composite_image_ref(
            background_asset_ref=fallback_ref,
            fx_prediction=prediction,
        )
        if not resolved.image_ref:
            raise RuntimeError("background prompt generation produced no usable output")
        emit_progress_event(
            stage="background_generation",
            status="completed",
            mode="prompt",
            image_ref=resolved.image_ref,
            used_fallback=bool(fallback_ref and resolved.image_ref == fallback_ref),
        )
        logger.info(
            "background generation completed output=%s fallback=%s duration=%s",
            resolved.image_ref,
            bool(fallback_ref and resolved.image_ref == fallback_ref),
            format_seconds(started),
        )
        background = build_background(resolved.image_ref, context.runtime)
        return (
            background,
            PromptStageRecord(
                mode="prompt",
                prompt=prompt,
                negative_prompt=negative_prompt,
                source_ref=fallback_ref or None,
                output_ref=background.asset_ref,
                used_fallback=bool(fallback_ref and resolved.image_ref == fallback_ref),
            ),
        )

    asset_ref = (background_asset_ref or "").strip()
    if not asset_ref:
        raise ValueError(
            "generate requires either background_asset_ref or background_prompt"
        )
    emit_progress_event(
        stage="background_generation",
        status="completed",
        mode="asset_ref",
        image_ref=asset_ref,
    )
    logger.info("background selection mode=asset_ref source=%s", asset_ref)
    background = build_background(asset_ref, context.runtime)
    return (
        background,
        PromptStageRecord(
            mode="asset_ref",
            source_ref=asset_ref,
            output_ref=background.asset_ref,
        ),
    )


def apply_background_canvas_upscale_if_needed(
    *,
    background: Background,
    context: AppContextLike,
    scene_dir: Path,
    upscaler_handle: ModelHandle,
    prompt: str,
    negative_prompt: str,
) -> Background:
    factor = max(1, int(getattr(context.runtime, "background_upscale_factor", 1)))
    if factor <= 1:
        return background
    source_path = Path(background.asset_ref)
    if not source_path.exists():
        return background
    output_path = (
        scene_dir / "assets" / "background" / "generated-background.canvas.png"
    )
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
    upscaled = _read_background_image_size(image_path=Path(canvas_ref))
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
) -> Background:
    factor = max(1, int(getattr(context.runtime, "background_upscale_factor", 1)))
    if factor <= 1:
        return background
    source_path = Path(background.asset_ref)
    if not source_path.exists():
        return background
    output_path = (
        scene_dir / "assets" / "background" / "generated-background.hiresfix.png"
    )
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
    with track_stage_vram(context, "background_detail_reconstruction"):
        prediction = context.background_upscaler_model.predict(
            upscaler_handle,
            FxRequest(
                mode="detail_reconstruct",
                image_ref=background.asset_ref,
                params={
                    "output_path": str(output_path),
                    "width": background.width,
                    "height": background.height,
                },
            ),
        )
    refined_ref = str(prediction.get("output_path") or output_path)
    refined = _read_background_image_size(image_path=Path(refined_ref))
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
) -> Background:
    background = apply_background_canvas_upscale_if_needed(
        background=background,
        context=context,
        scene_dir=scene_dir,
        upscaler_handle=upscaler_handle,
        prompt=prompt,
        negative_prompt=negative_prompt,
    )
    return apply_background_detail_reconstruction_if_needed(
        background=background,
        context=context,
        scene_dir=scene_dir,
        upscaler_handle=upscaler_handle,
        prompt=prompt,
        negative_prompt=negative_prompt,
    )


def _read_background_image_size(
    *,
    image_path: Path,
) -> dict[str, Any]:
    from PIL import Image  # type: ignore

    with Image.open(image_path).convert("RGB") as image:
        return {
            "path": image_path,
            "width": image.width,
            "height": image.height,
        }
