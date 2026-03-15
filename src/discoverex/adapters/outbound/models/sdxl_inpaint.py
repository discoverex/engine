from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.models.types import InpaintPrediction, InpaintRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .image_patch_ops import (
    apply_alpha_patch,
    crop_bbox,
    expand_bbox,
    load_image_rgb,
    sanitize_bbox,
    save_image,
)
from .pipeline_memory import OffloadMode
from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
    validate_diffusers_runtime,
)
from .runtime_cleanup import clear_model_runtime
from .sdxl_inpaint_inference import (
    build_bbox_mask,
    build_full_mask,
    extract_object_rgba,
    has_meaningful_mask,
    load_inpaint_pipe,
    normalize_generated_patch,
    resize_patch_to_long_side,
)

logger = get_logger("discoverex.models.sdxl_inpaint")


class SdxlInpaintModel:
    def __init__(
        self,
        model_id: str = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1",
        revision: str = "main",
        device: str = "cuda",
        dtype: str = "float16",
        precision: str = "fp16",
        batch_size: int = 1,
        seed: int | None = None,
        strict_runtime: bool = False,
        offload_mode: OffloadMode = "none",
        enable_attention_slicing: bool = False,
        enable_vae_slicing: bool = False,
        enable_vae_tiling: bool = False,
        enable_xformers_memory_efficient_attention: bool = False,
        enable_fp8_layerwise_casting: bool = False,
        enable_channels_last: bool = False,
        default_prompt: str = "place a visually coherent hidden object in the marked region",
        default_negative_prompt: str = "blurry, low quality, artifact",
        generation_strength: float = 0.5,
        generation_steps: int = 28,
        generation_guidance_scale: float = 7.0,
        mask_blur: int = 4,
        inpaint_only_masked: bool = True,
        masked_area_padding: int = 32,
        patch_target_long_side: int = 128,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.device = device
        self.dtype = dtype
        self.precision = precision
        self.batch_size = batch_size
        self.seed = seed
        self.strict_runtime = strict_runtime
        self.offload_mode = offload_mode
        self.enable_attention_slicing = enable_attention_slicing
        self.enable_vae_slicing = enable_vae_slicing
        self.enable_vae_tiling = enable_vae_tiling
        self.enable_xformers_memory_efficient_attention = (
            enable_xformers_memory_efficient_attention
        )
        self.enable_fp8_layerwise_casting = enable_fp8_layerwise_casting
        self.enable_channels_last = enable_channels_last
        self.default_prompt = default_prompt
        self.default_negative_prompt = default_negative_prompt
        self.generation_strength = generation_strength
        self.generation_steps = generation_steps
        self.generation_guidance_scale = generation_guidance_scale
        self.mask_blur = mask_blur
        self.inpaint_only_masked = inpaint_only_masked
        self.masked_area_padding = masked_area_padding
        self.patch_target_long_side = patch_target_long_side
        self._pipe: Any | None = None

    def load(self, model_ref_or_version: str) -> ModelHandle:
        logger.info(
            "loading object inpaint model model_id=%s revision=%s requested_device=%s",
            self.model_id,
            self.revision,
            self.device,
        )
        runtime = resolve_runtime()
        validate_diffusers_runtime(runtime)
        selected_device = resolve_device(self.device, runtime.torch)
        selected_dtype = str(normalize_dtype(self.dtype, runtime.torch))
        if self.strict_runtime and not runtime.available:
            raise RuntimeError(
                f"torch/transformers runtime unavailable: {runtime.reason}"
            )
        if self.strict_runtime and selected_device != self.device:
            raise RuntimeError(f"requested device '{self.device}' is unavailable")
        apply_seed(self.seed, runtime.torch)
        return ModelHandle(
            name="object_inpaint_model",
            version=model_ref_or_version,
            runtime="sdxl_inpaint",
            model_id=self.model_id,
            revision=self.revision,
            device=selected_device,
            dtype=selected_dtype,
            extra=build_runtime_extra(
                runtime=runtime,
                requested_device=self.device,
                selected_device=selected_device,
                requested_dtype=self.dtype,
                selected_dtype=selected_dtype,
                precision=self.precision,
                batch_size=self.batch_size,
                seed=self.seed,
            ),
        )

    def predict(
        self,
        handle: ModelHandle,
        request: InpaintRequest,
    ) -> InpaintPrediction:
        started = perf_counter()
        result: InpaintPrediction = {
            "region_id": request.region_id,
            "model_id": self.model_id,
            "inpaint_mode": "sdxl_inpaint",
            "quality_score": 0.9,
        }
        composited_ref = self._predict_and_inpaint(handle, request)
        if composited_ref is not None:
            result["patch_image_ref"] = str(composited_ref["patch"])
            result["object_image_ref"] = str(composited_ref["object"])
            result["object_mask_ref"] = str(composited_ref["mask"])
            result["composited_image_ref"] = str(composited_ref["composited"])
        logger.info(
            "object inpaint prediction completed region=%s object=%s composited=%s duration=%s",
            request.region_id,
            result.get("object_image_ref"),
            result.get("composited_image_ref"),
            format_seconds(started),
        )
        return result

    def _predict_and_inpaint(
        self,
        handle: ModelHandle,
        request: InpaintRequest,
    ) -> dict[str, Path] | None:
        if request.image_ref is None or request.bbox is None:
            return None
        source = Path(str(request.image_ref))
        output_path = request.output_path
        if not source.exists() or output_path is None:
            if self.strict_runtime:
                raise ValueError("object inpaint requires a real source image path")
            return None
        try:
            image = load_image_rgb(source)
            bbox = sanitize_bbox(request.bbox, image.width, image.height)
            crop_bbox_with_padding = expand_bbox(
                bbox,
                padding=(
                    request.masked_area_padding
                    if request.inpaint_only_masked
                    else 0
                ),
                width=image.width,
                height=image.height,
            )
            original_patch = crop_bbox(image, crop_bbox_with_padding)
            working_patch, working_size = resize_patch_to_long_side(
                original_patch, self.patch_target_long_side
            )
            mask = self._build_generation_mask(
                crop_bbox=crop_bbox_with_padding,
                target_bbox=bbox,
                working_size=working_size,
                request=request,
            )
            generated_patch = self._generate_image(
                handle=handle,
                image=working_patch,
                mask=mask,
                prompt=request.generation_prompt
                or request.prompt
                or self.default_prompt,
                negative_prompt=request.negative_prompt or self.default_negative_prompt,
                strength=float(request.generation_strength or self.generation_strength),
                num_inference_steps=int(
                    request.generation_steps or self.generation_steps
                ),
                guidance_scale=float(
                    request.generation_guidance_scale or self.generation_guidance_scale
                ),
                mask_blur=int(request.mask_blur or self.mask_blur),
                inpaint_only_masked=bool(
                    request.inpaint_only_masked
                    if request.inpaint_only_masked is not None
                    else self.inpaint_only_masked
                ),
                padding_mask_crop=(
                    int(request.masked_area_padding or self.masked_area_padding)
                    if (
                        request.inpaint_only_masked
                        if request.inpaint_only_masked is not None
                        else self.inpaint_only_masked
                    )
                    else None
                ),
            )
            generated_patch = normalize_generated_patch(generated_patch, working_size)
            output = Path(output_path)
            object_image, object_mask = extract_object_rgba(
                working_patch, generated_patch
            )
            if not has_meaningful_mask(object_mask):
                logger.warning(
                    "object inpaint produced no meaningful foreground region=%s",
                    request.region_id,
                )
                return None
            composited = apply_alpha_patch(image, object_image, bbox)
            composited_path = save_image(composited, output)
            patch_path = save_image(generated_patch, output.with_suffix(".patch.png"))
            object_path = save_image(object_image, output.with_suffix(".object.png"))
            mask_path = save_image(object_mask, output.with_suffix(".mask.png"))
            return {
                "patch": patch_path,
                "object": object_path,
                "mask": mask_path,
                "composited": composited_path,
            }
        except Exception:
            if self.strict_runtime:
                raise
            return None

    def _build_generation_mask(
        self,
        *,
        crop_bbox: tuple[int, int, int, int],
        target_bbox: tuple[int, int, int, int],
        working_size: tuple[int, int],
        request: InpaintRequest,
    ) -> Any:
        if not request.inpaint_only_masked:
            return build_full_mask(*working_size)
        crop_left, crop_top, crop_right, crop_bottom = crop_bbox
        crop_width = max(1, crop_right - crop_left)
        crop_height = max(1, crop_bottom - crop_top)
        target_left, target_top, target_right, target_bottom = target_bbox
        scale_x = working_size[0] / crop_width
        scale_y = working_size[1] / crop_height
        localized_bbox = (
            max(0, int(round((target_left - crop_left) * scale_x))),
            max(0, int(round((target_top - crop_top) * scale_y))),
            min(working_size[0], int(round((target_right - crop_left) * scale_x))),
            min(working_size[1], int(round((target_bottom - crop_top) * scale_y))),
        )
        return build_bbox_mask(
            crop_size=working_size,
            mask_bbox=localized_bbox,
            blur_radius=int(request.mask_blur or self.mask_blur),
        )

    def _generate_image(
        self,
        *,
        handle: ModelHandle,
        image: Any,
        mask: Any,
        prompt: str,
        negative_prompt: str,
        strength: float,
        num_inference_steps: int,
        guidance_scale: float,
        mask_blur: int,
        inpaint_only_masked: bool,
        padding_mask_crop: int | None,
    ) -> Any:
        self._pipe = load_inpaint_pipe(
            current_pipe=self._pipe,
            model_id=self.model_id,
            revision=self.revision,
            handle=handle,
            offload_mode=self.offload_mode,
            enable_attention_slicing=self.enable_attention_slicing,
            enable_vae_slicing=self.enable_vae_slicing,
            enable_vae_tiling=self.enable_vae_tiling,
            enable_xformers_memory_efficient_attention=self.enable_xformers_memory_efficient_attention,
            enable_fp8_layerwise_casting=self.enable_fp8_layerwise_casting,
            enable_channels_last=self.enable_channels_last,
        )
        pipe = self._pipe
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image,
            mask_image=mask,
            width=image.size[0],
            height=image.size[1],
            strength=strength,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            mask_blur=mask_blur,
            padding_mask_crop=padding_mask_crop if inpaint_only_masked else None,
        )
        images = getattr(result, "images", None)
        if not images:
            raise RuntimeError("inpainting pipeline returned no images")
        return images[0]

    def unload(self) -> None:
        clear_model_runtime(self._pipe)
        self._pipe = None
