from __future__ import annotations

from pathlib import Path
from time import perf_counter

from discoverex.adapters.outbound.models.sam_object_mask import SamObjectMaskExtractor
from discoverex.application.context import AppContextLike
from discoverex.domain.region import Region
from discoverex.models.types import FxRequest, ModelHandle
from discoverex.progress_events import emit_progress_event
from discoverex.runtime_logging import format_seconds, get_logger

from .assets import build_placement_assets, relocate_mask_assets
from .prompts import object_generation_prompt, resolve_object_prompts
from .types import GeneratedObjectAsset

logger = get_logger("discoverex.generate.objects")


def _stdout_debug(message: str) -> None:
    print(f"[discoverex-debug] {message}", flush=True)

_DEFAULT_OBJECT_NEGATIVE = (
    "busy scene, environment, multiple objects, floor, wall, clutter, blurry, artifact"
)
_OBJECT_GENERATION_SIZE = 512
_OBJECT_GENERATION_STEPS = 30
_OBJECT_GENERATION_GUIDANCE = 5.0


def _resolved_object_generation_steps(context: AppContextLike) -> int:
    value = getattr(
        context.object_generator_model,
        "default_num_inference_steps",
        _OBJECT_GENERATION_STEPS,
    )
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return _OBJECT_GENERATION_STEPS


def _resolved_object_generation_guidance(context: AppContextLike) -> float:
    value = getattr(
        context.object_generator_model,
        "default_guidance_scale",
        _OBJECT_GENERATION_GUIDANCE,
    )
    try:
        return float(value)
    except (TypeError, ValueError):
        return _OBJECT_GENERATION_GUIDANCE


def generate_region_objects(
    *,
    context: AppContextLike,
    scene_dir: Path,
    regions: list[Region],
    object_handle: ModelHandle,
    object_prompt: str,
    object_negative_prompt: str,
    object_generation_size: int = _OBJECT_GENERATION_SIZE,
    max_vram_gb: float | None = None,
) -> dict[str, GeneratedObjectAsset]:
    masker = SamObjectMaskExtractor(
        device=context.runtime.model_runtime.device,
        dtype=context.runtime.model_runtime.dtype,
    )
    generated: dict[str, GeneratedObjectAsset] = {}
    total_regions = len(regions)
    object_prompts = resolve_object_prompts(object_prompt, total_regions=total_regions)
    object_generation_steps = _resolved_object_generation_steps(context)
    object_generation_guidance = _resolved_object_generation_guidance(context)
    try:
        batch_size = max(1, int(context.runtime.model_runtime.batch_size))
        for batch_start in range(0, total_regions, batch_size):
            batch_regions = regions[batch_start : batch_start + batch_size]
            batch_prompts = object_prompts[batch_start : batch_start + batch_size]
            batch_paths: list[Path] = []
            for batch_index, region in enumerate(batch_regions, start=batch_start + 1):
                output_prefix = scene_dir / "assets" / "objects" / f"{region.region_id}"
                output_prefix.parent.mkdir(parents=True, exist_ok=True)
                candidate_path = output_prefix.with_suffix(".candidate.png")
                batch_paths.append(candidate_path)
                emit_progress_event(
                    stage="object_generation",
                    status="started",
                    region_id=region.region_id,
                    index=batch_index,
                    total=total_regions,
                    width=object_generation_size,
                    height=object_generation_size,
                )
            started = perf_counter()
            batch_prediction = None
            if batch_size > 1 and hasattr(context.object_generator_model, "predict_batch"):
                _stdout_debug(
                    f"object_batch_predict start batch_start={batch_start + 1} batch_size={len(batch_regions)} size={object_generation_size}"
                )
                batch_prediction = context.object_generator_model.predict_batch(
                    object_handle,
                    FxRequest(
                        mode="object_generation",
                        params={
                            "output_paths": [str(path) for path in batch_paths],
                            "prompts": [object_generation_prompt(prompt) for prompt in batch_prompts],
                            "width": object_generation_size,
                            "height": object_generation_size,
                            "seed": context.runtime.model_runtime.seed,
                            "negative_prompt": object_negative_prompt or _DEFAULT_OBJECT_NEGATIVE,
                            "num_inference_steps": object_generation_steps,
                            "guidance_scale": object_generation_guidance,
                            "max_vram_gb": max_vram_gb,
                        },
                    ),
                )
                _stdout_debug(
                    f"object_batch_predict end batch_start={batch_start + 1} saved={len(list(batch_prediction.get('output_paths') or []))}"
                )
            saved_paths = list(batch_prediction.get("output_paths") or []) if batch_prediction else []
            for offset, region in enumerate(batch_regions):
                index = batch_start + offset + 1
                region_prompt = batch_prompts[offset]
                output_prefix = scene_dir / "assets" / "objects" / f"{region.region_id}"
                candidate_path = batch_paths[offset]
                if not saved_paths:
                    _stdout_debug(
                        "object_predict start "
                        f"region={region.region_id} index={index} size={object_generation_size} "
                        f"prompt={region_prompt!r} negative_prompt={(object_negative_prompt or _DEFAULT_OBJECT_NEGATIVE)!r} "
                        f"steps={object_generation_steps} guidance={object_generation_guidance} "
                        f"seed={context.runtime.model_runtime.seed}"
                    )
                    prediction = context.object_generator_model.predict(
                        object_handle,
                        FxRequest(
                            mode="object_generation",
                            params={
                                "output_path": str(candidate_path),
                                "width": object_generation_size,
                                "height": object_generation_size,
                                "seed": context.runtime.model_runtime.seed,
                                "prompt": object_generation_prompt(region_prompt),
                                "negative_prompt": object_negative_prompt
                                or _DEFAULT_OBJECT_NEGATIVE,
                                "num_inference_steps": object_generation_steps,
                                "guidance_scale": object_generation_guidance,
                                "max_vram_gb": max_vram_gb,
                            },
                        ),
                    )
                    _stdout_debug(
                        f"object_predict end region={region.region_id} index={index}"
                    )
                    generated_ref = str(prediction.get("output_path") or candidate_path)
                else:
                    generated_ref = saved_paths[offset]
                _stdout_debug(
                    f"mask_extract start region={region.region_id} index={index} image={generated_ref}"
                )
                masked = masker.extract(
                    image_path=generated_ref,
                    output_prefix=output_prefix,
                )
                _stdout_debug(
                    "mask_extract end "
                    f"region={region.region_id} index={index} "
                    f"source={masked.get('mask_source', 'unknown')} "
                    f"alpha_has_signal={masked.get('alpha_has_signal', False)} "
                    f"alpha_bbox={masked.get('alpha_bbox', '')} "
                    f"alpha_nonzero_ratio={masked.get('alpha_nonzero_ratio', 0.0)} "
                    f"alpha_mean={masked.get('alpha_mean', 0.0)}"
                )
                mask_path, raw_alpha_path = relocate_mask_assets(
                    scene_dir=scene_dir,
                    masked=masked,
                )
                _stdout_debug(
                    f"placement_build start region={region.region_id} index={index}"
                )
                placement = build_placement_assets(
                    context=context,
                    object_path=Path(str(masked["object"])),
                    mask_path=mask_path,
                    raw_alpha_path=raw_alpha_path,
                )
                _stdout_debug(
                    f"placement_build end region={region.region_id} index={index} width={placement.width} height={placement.height}"
                )
                generated[region.region_id] = GeneratedObjectAsset(
                    region_id=region.region_id,
                    candidate_ref=generated_ref,
                    object_ref=str(placement.object_path),
                    object_mask_ref=str(placement.mask_path),
                    width=placement.width,
                    height=placement.height,
                    raw_alpha_mask_ref=str(placement.raw_alpha_path),
                    raw_generated_ref=generated_ref,
                    sam_object_ref=str(masked["object"]),
                    sam_mask_ref=str(mask_path),
                    mask_source=str(masked.get("mask_source", "unknown")),
                    tight_bbox=placement.tight_bbox,
                    object_prompt=region_prompt,
                    object_negative_prompt=object_negative_prompt
                    or _DEFAULT_OBJECT_NEGATIVE,
                    object_model_id=str(getattr(object_handle, "model_id", "") or ""),
                    object_sampler=str(
                        getattr(context.object_generator_model, "sampler", "") or ""
                    ),
                    object_steps=object_generation_steps,
                    object_guidance_scale=object_generation_guidance,
                    object_seed=context.runtime.model_runtime.seed,
                )
                emit_progress_event(
                    stage="object_generation",
                    status="completed",
                    region_id=region.region_id,
                    index=index,
                    total=total_regions,
                    candidate_image_ref=generated_ref,
                    object_image_ref=str(placement.object_path),
                    object_mask_ref=str(placement.mask_path),
                )
                logger.info(
                    "object generation completed region=%s candidate=%s object=%s duration=%s",
                    region.region_id,
                    generated_ref,
                    placement.object_path,
                    format_seconds(started),
                )
    finally:
        masker.unload()
    return generated
