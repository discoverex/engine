from __future__ import annotations

from pathlib import Path
from time import perf_counter

from discoverex.application.context import AppContextLike
from discoverex.domain.scene import Background
from discoverex.models.types import FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .composite_pipeline import resolve_composite_image_ref
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
        output_path = scene_dir / "layers" / "base" / "generated-background.png"
        logger.info(
            "background generation started mode=prompt output=%s size=%sx%s",
            output_path,
            int(context.runtime.width),
            int(context.runtime.height),
        )
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
        logger.info(
            "background generation completed output=%s fallback=%s duration=%s",
            resolved.image_ref,
            bool(fallback_ref and resolved.image_ref == fallback_ref),
            format_seconds(started),
        )
        return (
            build_background(resolved.image_ref, context.runtime),
            PromptStageRecord(
                mode="prompt",
                prompt=prompt,
                negative_prompt=negative_prompt,
                source_ref=fallback_ref or None,
                output_ref=resolved.image_ref,
                used_fallback=bool(fallback_ref and resolved.image_ref == fallback_ref),
            ),
        )

    asset_ref = (background_asset_ref or "").strip()
    if not asset_ref:
        raise ValueError(
            "generate requires either background_asset_ref or background_prompt"
        )
    logger.info("background selection mode=asset_ref source=%s", asset_ref)
    return (
        build_background(asset_ref, context.runtime),
        PromptStageRecord(
            mode="asset_ref",
            source_ref=asset_ref,
            output_ref=asset_ref,
        ),
    )
