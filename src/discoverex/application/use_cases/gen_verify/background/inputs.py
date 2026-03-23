from __future__ import annotations

from pathlib import Path
from time import perf_counter

from discoverex.application.context import AppContextLike
from discoverex.domain.scene import Background
from discoverex.models.types import FxRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from ..composite_pipeline import resolve_composite_image_ref
from ..runtime_metrics import track_stage_vram
from ..scene_builder import build_background
from ..types import PromptStageRecord
from ...exporting.shared import compose_display_name

_DEFAULT_BACKGROUND_NEGATIVE = "blurry, low quality, artifact"
logger = get_logger("discoverex.generate.background")


def _background_display_name(*, prompt: str, negative_prompt: str) -> str:
    return compose_display_name(
        prompt=prompt,
        negative_prompt=negative_prompt,
    ) or "background"


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
        if fx_handle is None:
            raise ValueError("background prompt mode requires fx_handle")
        return _build_generated_background(
            context=context,
            scene_dir=scene_dir,
            fx_handle=fx_handle,
            background_asset_ref=background_asset_ref,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )
    return _build_selected_background(
        context=context,
        background_asset_ref=background_asset_ref,
    )


def _build_generated_background(
    *,
    context: AppContextLike,
    scene_dir: Path,
    fx_handle: ModelHandle,
    background_asset_ref: str | None,
    prompt: str,
    negative_prompt: str,
) -> tuple[Background, PromptStageRecord]:
    started = perf_counter()
    output_path = scene_dir / "assets" / "background" / "generated-background.png"
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
    background.metadata["prompt"] = prompt
    background.metadata["negative_prompt"] = negative_prompt or _DEFAULT_BACKGROUND_NEGATIVE
    background.metadata["name"] = _background_display_name(
        prompt=prompt,
        negative_prompt=negative_prompt or _DEFAULT_BACKGROUND_NEGATIVE,
    )
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


def _build_selected_background(
    *,
    context: AppContextLike,
    background_asset_ref: str | None,
) -> tuple[Background, PromptStageRecord]:
    asset_ref = (background_asset_ref or "").strip()
    if not asset_ref:
        raise ValueError("generate requires either background_asset_ref or background_prompt")
    emit_progress_event(
        stage="background_generation",
        status="completed",
        mode="asset_ref",
        image_ref=asset_ref,
    )
    logger.info("background selection mode=asset_ref source=%s", asset_ref)
    background = build_background(asset_ref, context.runtime)
    background.metadata["name"] = Path(asset_ref).stem or "background"
    return (
        background,
        PromptStageRecord(
            mode="asset_ref",
            source_ref=asset_ref,
            output_ref=background.asset_ref,
        ),
    )
