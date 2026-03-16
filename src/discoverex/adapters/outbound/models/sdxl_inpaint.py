from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.models.types import InpaintPrediction, InpaintRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .image_patch_ops import (
    apply_alpha_patch,
    apply_alpha_patch_with_opacity,
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
        inpaint_mode: str = "sdxl_inpaint",
        overlay_alpha: float = 0.5,
        placement_grid_stride: int = 24,
        placement_downscale_factor: int = 2,
        similarity_color_weight: float = 0.7,
        similarity_edge_weight: float = 0.3,
        placement_overlap_threshold: float = 0.35,
        independent_object_generation: bool = False,
        object_generation_background: str = "average",
        final_inpaint_strength: float | None = None,
        final_inpaint_steps: int | None = None,
        final_inpaint_guidance_scale: float | None = None,
        final_inpaint_only_masked: bool = False,
        final_mask_blur: int | None = None,
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
        self.inpaint_mode = inpaint_mode
        self.overlay_alpha = overlay_alpha
        self.placement_grid_stride = placement_grid_stride
        self.placement_downscale_factor = placement_downscale_factor
        self.similarity_color_weight = similarity_color_weight
        self.similarity_edge_weight = similarity_edge_weight
        self.placement_overlap_threshold = placement_overlap_threshold
        self.independent_object_generation = independent_object_generation
        self.object_generation_background = object_generation_background
        self.final_inpaint_strength = final_inpaint_strength
        self.final_inpaint_steps = final_inpaint_steps
        self.final_inpaint_guidance_scale = final_inpaint_guidance_scale
        self.final_inpaint_only_masked = final_inpaint_only_masked
        self.final_mask_blur = final_mask_blur
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
            "inpaint_mode": self.inpaint_mode,
            "quality_score": 0.9,
        }
        composited_ref = self._predict_and_inpaint(handle, request)
        if composited_ref is not None:
            result["patch_image_ref"] = str(composited_ref["patch"])
            if "candidate" in composited_ref:
                result["candidate_image_ref"] = str(composited_ref["candidate"])
            result["object_image_ref"] = str(composited_ref["object"])
            result["object_mask_ref"] = str(composited_ref["mask"])
            result["composited_image_ref"] = str(composited_ref["composited"])
            if "precomposited" in composited_ref:
                result["precomposited_image_ref"] = str(
                    composited_ref["precomposited"]
                )
            if "blend_mask" in composited_ref:
                result["blend_mask_ref"] = str(composited_ref["blend_mask"])
            if "selected_bbox" in composited_ref:
                left, top, right, bottom = composited_ref["selected_bbox"]
                result["selected_bbox"] = {
                    "x": float(left),
                    "y": float(top),
                    "w": float(right - left),
                    "h": float(bottom - top),
                }
            if "placement_score" in composited_ref:
                result["placement_score"] = float(composited_ref["placement_score"])
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
    ) -> dict[str, Any] | None:
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
            if (
                self.inpaint_mode == "similarity_overlay_v2"
                and request.object_image_ref is not None
                and request.object_mask_ref is not None
            ):
                return self._predict_with_generated_object_v2(
                    image=image,
                    bbox=bbox,
                    handle=handle,
                    output=Path(output_path),
                    request=request,
                )
            initial_source = image
            initial_force_full_mask = False
            if (
                self.inpaint_mode == "similarity_overlay_v2"
                and self.independent_object_generation
            ):
                initial_source = self._build_object_generation_canvas(
                    image=image,
                    bbox=bbox,
                )
                initial_force_full_mask = True
            initial_stage = self._run_inpaint_stage(
                handle=handle,
                source_image=initial_source,
                target_bbox=bbox,
                request=request,
                force_full_mask=initial_force_full_mask,
            )
            output = Path(output_path)
            if not has_meaningful_mask(initial_stage["object_mask"]):
                logger.warning(
                    "object inpaint produced no meaningful foreground region=%s",
                    request.region_id,
                )
                return None
            if self.inpaint_mode == "similarity_overlay_v2":
                return self._predict_with_similarity_overlay_v2(
                    image=image,
                    bbox=bbox,
                    initial_stage=initial_stage,
                    handle=handle,
                    output=output,
                    request=request,
                )
            composited = apply_alpha_patch(image, initial_stage["object_image"], bbox)
            return self._save_stage_outputs(
                output=output,
                patch=initial_stage["generated_patch"],
                object_image=initial_stage["object_image"],
                object_mask=initial_stage["object_mask"],
                composited=composited,
            )
        except Exception:
            if self.strict_runtime:
                raise
            return None

    def _predict_with_generated_object_v2(
        self,
        *,
        image: Any,
        bbox: tuple[int, int, int, int],
        handle: ModelHandle,
        output: Path,
        request: InpaintRequest,
    ) -> dict[str, Any]:
        object_image, object_mask = self._load_object_assets(request=request)
        placement_bbox, placement_score = self._find_similarity_placement(
            image=image,
            patch=object_image,
            mask=object_mask,
            fallback_bbox=bbox,
        )
        precomposited = apply_alpha_patch_with_opacity(
            image,
            object_image,
            placement_bbox,
            opacity=self.overlay_alpha,
        )
        precomposited_path = save_image(
            precomposited, output.with_suffix(".precomposite.png")
        )
        blend_stage = self._run_blend_stage(
            handle=handle,
            source_image=precomposited,
            target_bbox=placement_bbox,
            object_image=object_image,
            object_mask=object_mask,
            request=request,
        )
        patch_path = save_image(
            blend_stage["generated_patch"], output.with_suffix(".patch.png")
        )
        composited_path = save_image(blend_stage["composited"], output)
        blend_mask_path = save_image(
            blend_stage["blend_mask"], output.with_suffix(".blend-mask.png")
        )
        candidate_ref = request.object_candidate_ref or request.object_image_ref
        if candidate_ref is None:
            raise ValueError("generated object candidate ref is required")
        return {
            "patch": patch_path,
            "candidate": Path(str(candidate_ref)),
            "object": Path(str(request.object_image_ref)),
            "mask": Path(str(request.object_mask_ref)),
            "composited": composited_path,
            "precomposited": precomposited_path,
            "blend_mask": blend_mask_path,
            "selected_bbox": placement_bbox,
            "placement_score": placement_score,
        }

    def _predict_with_similarity_overlay_v2(
        self,
        *,
        image: Any,
        bbox: tuple[int, int, int, int],
        initial_stage: dict[str, Any],
        handle: ModelHandle,
        output: Path,
        request: InpaintRequest,
    ) -> dict[str, Any]:
        placement_bbox, placement_score = self._find_similarity_placement(
            image=image,
            patch=initial_stage["object_image"],
            mask=initial_stage["object_mask"],
            fallback_bbox=bbox,
        )
        precomposited = apply_alpha_patch_with_opacity(
            image,
            initial_stage["object_image"],
            placement_bbox,
            opacity=self.overlay_alpha,
        )
        precomposited_path = save_image(
            precomposited, output.with_suffix(".precomposite.png")
        )
        candidate_path = save_image(
            initial_stage["object_image"], output.with_suffix(".candidate.png")
        )
        final_stage = self._run_inpaint_stage(
            handle=handle,
            source_image=precomposited,
            target_bbox=placement_bbox,
            request=request.model_copy(
                update={
                    "generation_strength": (
                        self.final_inpaint_strength
                        if self.final_inpaint_strength is not None
                        else min(
                            float(request.generation_strength or self.generation_strength),
                            0.18,
                        )
                    ),
                    "generation_steps": (
                        self.final_inpaint_steps
                        if self.final_inpaint_steps is not None
                        else max(
                            4,
                            min(int(request.generation_steps or self.generation_steps), 6),
                        )
                    ),
                    "generation_guidance_scale": (
                        self.final_inpaint_guidance_scale
                        if self.final_inpaint_guidance_scale is not None
                        else min(
                            float(
                                request.generation_guidance_scale
                                or self.generation_guidance_scale
                            ),
                            2.0,
                        )
                    ),
                    "inpaint_only_masked": self.final_inpaint_only_masked,
                    "mask_blur": (
                        self.final_mask_blur
                        if self.final_mask_blur is not None
                        else int(request.mask_blur or self.mask_blur)
                    ),
                }
            ),
        )
        use_stage = (
            final_stage
            if has_meaningful_mask(final_stage["object_mask"])
            else initial_stage
        )
        composited = apply_alpha_patch(image, use_stage["object_image"], placement_bbox)
        saved = self._save_stage_outputs(
            output=output,
            patch=use_stage["generated_patch"],
            object_image=use_stage["object_image"],
            object_mask=use_stage["object_mask"],
            composited=composited,
        )
        return {
            **saved,
            "candidate": candidate_path,
            "precomposited": precomposited_path,
            "selected_bbox": placement_bbox,
            "placement_score": placement_score,
        }

    def _run_inpaint_stage(
        self,
        *,
        handle: ModelHandle,
        source_image: Any,
        target_bbox: tuple[int, int, int, int],
        request: InpaintRequest,
        force_full_mask: bool = False,
    ) -> dict[str, Any]:
        request_inpaint_only_masked = (
            request.inpaint_only_masked
            if request.inpaint_only_masked is not None
            else self.inpaint_only_masked
        )
        crop_bbox_with_padding = expand_bbox(
            target_bbox,
            padding=(request.masked_area_padding if request_inpaint_only_masked else 0),
            width=source_image.width,
            height=source_image.height,
        )
        if force_full_mask:
            crop_bbox_with_padding = (0, 0, source_image.width, source_image.height)
        original_patch = crop_bbox(source_image, crop_bbox_with_padding)
        working_patch, working_size = resize_patch_to_long_side(
            original_patch, self.patch_target_long_side
        )
        mask = self._build_generation_mask(
            crop_bbox=crop_bbox_with_padding,
            target_bbox=target_bbox,
            working_size=working_size,
            request=request,
            force_full_mask=force_full_mask,
        )
        generated_patch = self._generate_image(
            handle=handle,
            image=working_patch,
            mask=mask,
            prompt=request.generation_prompt or request.prompt or self.default_prompt,
            negative_prompt=request.negative_prompt or self.default_negative_prompt,
            strength=float(request.generation_strength or self.generation_strength),
            num_inference_steps=int(request.generation_steps or self.generation_steps),
            guidance_scale=float(
                request.generation_guidance_scale or self.generation_guidance_scale
            ),
            mask_blur=int(request.mask_blur or self.mask_blur),
            inpaint_only_masked=bool(request_inpaint_only_masked),
            padding_mask_crop=(
                int(request.masked_area_padding or self.masked_area_padding)
                if request_inpaint_only_masked
                else None
            ),
        )
        generated_patch = normalize_generated_patch(generated_patch, working_size)
        object_image, object_mask = extract_object_rgba(working_patch, generated_patch)
        return {
            "generated_patch": generated_patch,
            "object_image": object_image,
            "object_mask": object_mask,
        }

    def _save_stage_outputs(
        self,
        *,
        output: Path,
        patch: Any,
        object_image: Any,
        object_mask: Any,
        composited: Any,
    ) -> dict[str, Path]:
        composited_path = save_image(composited, output)
        patch_path = save_image(patch, output.with_suffix(".patch.png"))
        object_path = save_image(object_image, output.with_suffix(".object.png"))
        mask_path = save_image(object_mask, output.with_suffix(".mask.png"))
        return {
            "patch": patch_path,
            "object": object_path,
            "mask": mask_path,
            "composited": composited_path,
        }

    def _run_blend_stage(
        self,
        *,
        handle: ModelHandle,
        source_image: Any,
        target_bbox: tuple[int, int, int, int],
        object_image: Any,
        object_mask: Any,
        request: InpaintRequest,
    ) -> dict[str, Any]:
        del handle, request
        localized_object = object_image.convert("RGBA").resize(
            (
                max(1, target_bbox[2] - target_bbox[0]),
                max(1, target_bbox[3] - target_bbox[1]),
            )
        )
        blend_mask = self._build_blend_mask(
            crop_bbox=target_bbox,
            target_bbox=target_bbox,
            working_size=localized_object.size,
            object_mask=object_mask,
        )
        generated_patch = self._harmonize_object_layer(
            background_image=source_image,
            object_image=localized_object,
            object_mask=blend_mask,
            target_bbox=target_bbox,
        )
        composited = apply_alpha_patch(
            source_image,
            generated_patch,
            target_bbox,
        )
        return {
            "generated_patch": generated_patch,
            "composited": composited,
            "blend_mask": blend_mask,
        }

    def _harmonize_object_layer(
        self,
        *,
        background_image: Any,
        object_image: Any,
        object_mask: Any,
        target_bbox: tuple[int, int, int, int],
    ) -> Any:
        import numpy as np
        from PIL import Image  # type: ignore

        background_crop = crop_bbox(background_image, target_bbox).convert("RGB")
        object_rgba = object_image.convert("RGBA")
        alpha_mask = object_rgba.getchannel("A")
        if object_mask is not None:
            alpha_mask = Image.fromarray(
                np.minimum(
                    np.asarray(alpha_mask, dtype=np.uint8),
                    np.asarray(object_mask.convert("L"), dtype=np.uint8),
                ),
                mode="L",
            )
        object_rgba.putalpha(alpha_mask)
        obj_arr = np.asarray(object_rgba, dtype=np.float32)
        bg_arr = np.asarray(background_crop, dtype=np.float32)
        alpha = obj_arr[..., 3:4] / 255.0
        if float(alpha.max()) <= 0.0:
            return object_rgba
        ring = np.asarray(object_mask.convert("L"), dtype=np.float32)[..., None] / 255.0
        obj_rgb = obj_arr[..., :3]
        obj_region = alpha[..., 0] > 0.1
        bg_mean = bg_arr.mean(axis=(0, 1), keepdims=True)
        if bool(obj_region.any()):
            obj_mean = obj_rgb[obj_region].mean(axis=0, keepdims=True).reshape(1, 1, 3)
        else:
            obj_mean = obj_rgb.mean(axis=(0, 1), keepdims=True)
        shifted = np.clip(obj_rgb + (bg_mean - obj_mean) * 0.35, 0.0, 255.0)
        core = (alpha >= 0.9).astype(np.float32)
        edge = ring * (alpha > 0.0).astype(np.float32) * (1.0 - core)
        harmonized_rgb = obj_rgb * (1.0 - edge) + shifted * edge
        harmonized_rgb = harmonized_rgb * (1.0 - edge * 0.18) + bg_arr * (edge * 0.18)
        final_alpha = np.clip(alpha * (1.0 - edge * 0.08), 0.0, 1.0)
        final = np.concatenate(
            [harmonized_rgb, final_alpha * 255.0],
            axis=2,
        ).astype(np.uint8)
        return Image.fromarray(final, mode="RGBA")

    def _build_blend_mask(
        self,
        *,
        crop_bbox: tuple[int, int, int, int],
        target_bbox: tuple[int, int, int, int],
        working_size: tuple[int, int],
        object_mask: Any,
    ) -> Any:
        from PIL import ImageChops, ImageFilter  # type: ignore

        localized_mask = self._localize_object_mask(
            crop_bbox=crop_bbox,
            target_bbox=target_bbox,
            working_size=working_size,
            object_mask=object_mask,
        )
        outer = localized_mask.filter(ImageFilter.MaxFilter(9))
        inner = localized_mask.filter(ImageFilter.MaxFilter(3))
        ring = ImageChops.subtract(outer, inner)
        ring = ring.filter(
            ImageFilter.GaussianBlur(radius=max(1, int(self.final_mask_blur or 4)))
        )
        if ring.getbbox() is None:
            return localized_mask
        return ring

    def _localize_object_mask(
        self,
        *,
        crop_bbox: tuple[int, int, int, int],
        target_bbox: tuple[int, int, int, int],
        working_size: tuple[int, int],
        object_mask: Any,
    ) -> Any:
        from PIL import Image  # type: ignore

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
        region_w = max(1, localized_bbox[2] - localized_bbox[0])
        region_h = max(1, localized_bbox[3] - localized_bbox[1])
        resized_mask = object_mask.convert("L").resize((region_w, region_h))
        canvas = Image.new("L", working_size, color=0)
        canvas.paste(resized_mask, (localized_bbox[0], localized_bbox[1]))
        return canvas

    def _apply_patch_to_crop(
        self,
        *,
        image: Any,
        patch: Any,
        crop_bbox: tuple[int, int, int, int],
    ) -> Any:
        composited = image.copy()
        composited.paste(
            patch.resize(
                (
                    max(1, crop_bbox[2] - crop_bbox[0]),
                    max(1, crop_bbox[3] - crop_bbox[1]),
                )
            ),
            (crop_bbox[0], crop_bbox[1]),
        )
        return composited

    def _load_object_assets(self, *, request: InpaintRequest) -> tuple[Any, Any]:
        from PIL import Image  # type: ignore

        if request.object_image_ref is None or request.object_mask_ref is None:
            raise ValueError("generated object refs are required for similarity_overlay_v2")
        object_image = Image.open(request.object_image_ref).convert("RGBA")
        object_mask = Image.open(request.object_mask_ref).convert("L")
        return object_image, object_mask

    def _find_similarity_placement(
        self,
        *,
        image: Any,
        patch: Any,
        mask: Any,
        fallback_bbox: tuple[int, int, int, int],
    ) -> tuple[tuple[int, int, int, int], float]:
        try:
            import numpy as np
        except Exception:
            return fallback_bbox, 0.0

        left, top, right, bottom = fallback_bbox
        region_w = max(1, right - left)
        region_h = max(1, bottom - top)
        scale = max(1, int(self.placement_downscale_factor))
        stride = max(1, int(self.placement_grid_stride))
        scaled_w = max(1, region_w // scale)
        scaled_h = max(1, region_h // scale)
        patch_small = patch.convert("RGB").resize((scaled_w, scaled_h))
        mask_small = mask.convert("L").resize((scaled_w, scaled_h))
        image_small = image.convert("RGB").resize(
            (max(1, image.width // scale), max(1, image.height // scale))
        )

        patch_arr = np.asarray(patch_small, dtype=np.float32)
        mask_arr = np.asarray(mask_small, dtype=np.float32) / 255.0
        valid = mask_arr > 0.05
        if int(valid.sum()) < 9:
            return fallback_bbox, 0.0
        patch_edges = self._compute_edge_map(patch_arr)
        image_arr = np.asarray(image_small, dtype=np.float32)
        image_h, image_w = image_arr.shape[:2]
        scaled_stride = max(1, stride // scale)

        positions = {
            (0, 0),
        }
        fallback_scaled = (
            min(max(0, left // scale), max(0, image_w - scaled_w)),
            min(max(0, top // scale), max(0, image_h - scaled_h)),
            min(max(0, left // scale), max(0, image_w - scaled_w)) + scaled_w,
            min(max(0, top // scale), max(0, image_h - scaled_h)) + scaled_h,
        )
        for y in range(0, max(1, image_h - scaled_h + 1), scaled_stride):
            positions.add((0, y))
            max_x = max(1, image_w - scaled_w + 1)
            for x in range(0, max_x, scaled_stride):
                positions.add((x, y))
        best_bbox = fallback_bbox
        best_score = float("inf")
        found_non_overlap = False
        for x, y in positions:
            if x + scaled_w > image_w or y + scaled_h > image_h:
                continue
            candidate_scaled = (x, y, x + scaled_w, y + scaled_h)
            overlap = self._bbox_iou(candidate_scaled, fallback_scaled)
            if overlap > self.placement_overlap_threshold:
                continue
            candidate = image_arr[y : y + scaled_h, x : x + scaled_w, :]
            color_diff = float(
                np.mean(np.abs(candidate[valid] - patch_arr[valid])) / 255.0
            )
            candidate_edges = self._compute_edge_map(candidate)
            edge_diff = float(
                np.mean(np.abs(candidate_edges[valid] - patch_edges[valid])) / 255.0
            )
            score = (
                self.similarity_color_weight * color_diff
                + self.similarity_edge_weight * edge_diff
            )
            if score < best_score:
                found_non_overlap = True
                real_left = min(max(0, x * scale), max(0, image.width - region_w))
                real_top = min(max(0, y * scale), max(0, image.height - region_h))
                best_bbox = (
                    real_left,
                    real_top,
                    real_left + region_w,
                    real_top + region_h,
                )
                best_score = score
        if not found_non_overlap:
            return fallback_bbox, 0.0
        placement_score = max(0.0, 1.0 - min(best_score, 1.0))
        return best_bbox, placement_score

    def _compute_edge_map(self, image_arr: Any) -> Any:
        try:
            import numpy as np
        except Exception:
            return image_arr[..., 0]
        gray = (
            0.299 * image_arr[..., 0]
            + 0.587 * image_arr[..., 1]
            + 0.114 * image_arr[..., 2]
        )
        grad_x = np.zeros_like(gray)
        grad_y = np.zeros_like(gray)
        grad_x[:, 1:] = np.abs(gray[:, 1:] - gray[:, :-1])
        grad_y[1:, :] = np.abs(gray[1:, :] - gray[:-1, :])
        return grad_x + grad_y

    def _bbox_iou(
        self,
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> float:
        left = max(first[0], second[0])
        top = max(first[1], second[1])
        right = min(first[2], second[2])
        bottom = min(first[3], second[3])
        inter_w = max(0, right - left)
        inter_h = max(0, bottom - top)
        intersection = inter_w * inter_h
        if intersection <= 0:
            return 0.0
        first_area = max(1, (first[2] - first[0]) * (first[3] - first[1]))
        second_area = max(1, (second[2] - second[0]) * (second[3] - second[1]))
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0

    def _build_object_generation_canvas(
        self,
        *,
        image: Any,
        bbox: tuple[int, int, int, int],
    ) -> Any:
        from PIL import Image

        if self.object_generation_background == "gray":
            return Image.new("RGB", image.size, color=(127, 127, 127))
        if self.object_generation_background == "black":
            return Image.new("RGB", image.size, color=(0, 0, 0))
        crop = crop_bbox(image, bbox).convert("RGB")
        avg = crop.resize((1, 1)).getpixel((0, 0))
        return Image.new("RGB", image.size, color=avg)

    def _build_generation_mask(
        self,
        *,
        crop_bbox: tuple[int, int, int, int],
        target_bbox: tuple[int, int, int, int],
        working_size: tuple[int, int],
        request: InpaintRequest,
        force_full_mask: bool = False,
    ) -> Any:
        if force_full_mask:
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
