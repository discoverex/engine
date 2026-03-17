from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.models.types import InpaintPrediction, InpaintRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .hidden_object_backends import (
    BackendRuntime,
    DiffusionObjectBlendBackend,
    IcLightRelighter,
    Rmbg20MaskRefiner,
    Sam2MaskRefiner,
)
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
        final_context_size: int = 512,
        independent_object_generation: bool = False,
        object_generation_background: str = "average",
        final_inpaint_strength: float | None = None,
        final_inpaint_steps: int | None = None,
        final_inpaint_guidance_scale: float | None = None,
        final_inpaint_only_masked: bool = False,
        final_mask_blur: int | None = None,
        pre_match_scale_ratio: tuple[float, float] = (0.04, 0.18),
        pre_match_rotation_deg: tuple[float, float] = (-25.0, 25.0),
        pre_match_saturation_mul: tuple[float, float] = (0.85, 0.97),
        pre_match_contrast_mul: tuple[float, float] = (0.90, 0.98),
        pre_match_sharpness_mul: tuple[float, float] = (0.85, 0.95),
        pre_match_variant_count: int = 5,
        composite_feather_px: int = 2,
        edge_blend_steps: int = 20,
        edge_blend_cfg: float = 4.5,
        edge_blend_strength: float = 0.18,
        edge_blend_ring_dilate_px: int = 10,
        core_blend_steps: int = 24,
        core_blend_cfg: float = 5.0,
        core_blend_strength: float = 0.35,
        shadow_blur_px: int = 12,
        shadow_opacity: float = 0.14,
        final_polish_steps: int = 14,
        final_polish_cfg: float = 4.0,
        final_polish_strength: float = 0.12,
        relight_method: str = "",
        edge_blend_backend: str = "",
        core_blend_backend: str = "",
        final_polish_backend: str = "",
        mask_refine_backend: str = "",
        rmbg_model_id: str = "",
        sam2_model_id: str = "",
        ic_light_model_id: str = "",
        edge_blend_model_id: str = "",
        core_blend_model_id: str = "",
        final_polish_model_id: str = "",
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
        self.final_context_size = final_context_size
        self.independent_object_generation = independent_object_generation
        self.object_generation_background = object_generation_background
        self.final_inpaint_strength = final_inpaint_strength
        self.final_inpaint_steps = final_inpaint_steps
        self.final_inpaint_guidance_scale = final_inpaint_guidance_scale
        self.final_inpaint_only_masked = final_inpaint_only_masked
        self.final_mask_blur = final_mask_blur
        self.pre_match_scale_ratio = pre_match_scale_ratio
        self.pre_match_rotation_deg = pre_match_rotation_deg
        self.pre_match_saturation_mul = pre_match_saturation_mul
        self.pre_match_contrast_mul = pre_match_contrast_mul
        self.pre_match_sharpness_mul = pre_match_sharpness_mul
        self.pre_match_variant_count = pre_match_variant_count
        self.composite_feather_px = composite_feather_px
        self.edge_blend_steps = edge_blend_steps
        self.edge_blend_cfg = edge_blend_cfg
        self.edge_blend_strength = edge_blend_strength
        self.edge_blend_ring_dilate_px = edge_blend_ring_dilate_px
        self.core_blend_steps = core_blend_steps
        self.core_blend_cfg = core_blend_cfg
        self.core_blend_strength = core_blend_strength
        self.shadow_blur_px = shadow_blur_px
        self.shadow_opacity = shadow_opacity
        self.final_polish_steps = final_polish_steps
        self.final_polish_cfg = final_polish_cfg
        self.final_polish_strength = final_polish_strength
        self.relight_method = relight_method
        self.edge_blend_backend = edge_blend_backend
        self.core_blend_backend = core_blend_backend
        self.final_polish_backend = final_polish_backend
        self.mask_refine_backend = mask_refine_backend
        self.rmbg_model_id = rmbg_model_id
        self.sam2_model_id = sam2_model_id
        self.ic_light_model_id = ic_light_model_id
        self.edge_blend_model_id = edge_blend_model_id
        self.core_blend_model_id = core_blend_model_id
        self.final_polish_model_id = final_polish_model_id
        self._pipe: Any | None = None
        self._rmbg_refiner: Rmbg20MaskRefiner | None = None
        self._sam2_refiner: Sam2MaskRefiner | None = None
        self._ic_light_relighter: IcLightRelighter | None = None
        self._edge_blend_pipe: DiffusionObjectBlendBackend | None = None
        self._core_blend_pipe: DiffusionObjectBlendBackend | None = None
        self._final_polish_pipe: DiffusionObjectBlendBackend | None = None

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
            if "edge_mask" in composited_ref:
                result["edge_mask_ref"] = str(composited_ref["edge_mask"])
            if "core_mask" in composited_ref:
                result["core_mask_ref"] = str(composited_ref["core_mask"])
            if "shadow" in composited_ref:
                result["shadow_ref"] = str(composited_ref["shadow"])
            if "edge_blend" in composited_ref:
                result["edge_blend_ref"] = str(composited_ref["edge_blend"])
            if "core_blend" in composited_ref:
                result["core_blend_ref"] = str(composited_ref["core_blend"])
            if "final_polish" in composited_ref:
                result["final_polish_ref"] = str(composited_ref["final_polish"])
            if "variant_manifest" in composited_ref:
                result["variant_manifest_ref"] = str(composited_ref["variant_manifest"])
            if "placement_variant_id" in composited_ref:
                result["placement_variant_id"] = str(composited_ref["placement_variant_id"])
            if "mask_source" in composited_ref:
                result["mask_source"] = str(composited_ref["mask_source"])
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
            if (
                self.inpaint_mode == "layerdiffuse_hidden_object_v1"
                and request.object_image_ref is not None
                and request.object_mask_ref is not None
            ):
                return self._predict_with_layerdiffuse_hidden_object_v1(
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

    def _predict_with_layerdiffuse_hidden_object_v1(
        self,
        *,
        image: Any,
        bbox: tuple[int, int, int, int],
        handle: ModelHandle,
        output: Path,
        request: InpaintRequest,
    ) -> dict[str, Any]:
        self._validate_hidden_object_backends()
        object_image, object_mask = self._load_object_assets(request=request)
        refined_mask = self._refine_hidden_object_mask(
            image=object_image.convert("RGB"),
            fallback_mask=object_mask,
        )
        object_image = object_image.convert("RGBA")
        object_image.putalpha(refined_mask)
        refined_object_path = save_image(
            object_image, output.with_suffix(".object.png")
        )
        refined_mask_path = save_image(
            refined_mask, output.with_suffix(".mask.png")
        )
        variants = self._build_pre_match_variants(
            image=image,
            bbox=bbox,
            object_image=object_image,
            object_mask=refined_mask,
        )
        selected_variant, placement_bbox, placement_score = self._select_best_variant(
            image=image,
            bbox=bbox,
            variants=variants,
        )
        variant_manifest_path = output.with_suffix(".variants.json")
        variant_manifest_path.write_text(
            json.dumps(
                {
                    "selected_variant_id": selected_variant["id"],
                    "variants": [
                        {
                            "id": variant["id"],
                            "score": round(float(variant.get("score", 0.0)), 6),
                            "scale_ratio": variant["scale_ratio"],
                            "rotation_deg": variant["rotation_deg"],
                            "saturation_mul": variant["saturation_mul"],
                            "contrast_mul": variant["contrast_mul"],
                            "sharpness_mul": variant["sharpness_mul"],
                            "placement_bbox": list(variant.get("placement_bbox", bbox)),
                        }
                        for variant in variants
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        precomposited, blend_mask = self._opaque_composite_object(
            image=image,
            object_image=selected_variant["object_image"],
            object_mask=selected_variant["object_mask"],
            target_bbox=placement_bbox,
        )
        precomposited_path = save_image(
            precomposited, output.with_suffix(".precomposite.png")
        )
        core_stage = self._run_object_blend_pass(
            handle=handle,
            source_image=precomposited,
            target_bbox=placement_bbox,
            localized_mask=selected_variant["object_mask"],
            prompt=(
                "harmonize the pasted object's texture, tone, and lighting with the "
                "surrounding scene while preserving object shape"
            ),
            negative_prompt=request.negative_prompt or self.default_negative_prompt,
            strength=self.core_blend_strength,
            num_inference_steps=self.core_blend_steps,
            guidance_scale=self.core_blend_cfg,
            backend_kind="core",
        )
        shadowed = self._apply_direct_shadow(
            image=core_stage["composited"],
            object_mask=selected_variant["object_mask"],
            target_bbox=placement_bbox,
        )
        shadow_path = save_image(shadowed, output.with_suffix(".shadow.png"))
        final_stage = self._run_object_blend_pass(
            handle=handle,
            source_image=shadowed,
            target_bbox=placement_bbox,
            localized_mask=selected_variant["object_mask"],
            prompt=(
                "perform a light final polish so the hidden object feels embedded in "
                "the scene without changing its identity"
            ),
            negative_prompt=request.negative_prompt or self.default_negative_prompt,
            strength=self.final_polish_strength,
            num_inference_steps=self.final_polish_steps,
            guidance_scale=self.final_polish_cfg,
            backend_kind="final",
        )
        composited_path = save_image(final_stage["composited"], output)
        patch_path = save_image(
            final_stage["generated_patch"], output.with_suffix(".patch.png")
        )
        core_mask_path = save_image(core_stage["blend_mask"], output.with_suffix(".core-mask.png"))
        core_patch_path = save_image(
            core_stage["generated_patch"], output.with_suffix(".core-blend.png")
        )
        final_patch_path = save_image(
            final_stage["generated_patch"], output.with_suffix(".final-polish.png")
        )
        candidate_ref = request.object_candidate_ref or request.object_image_ref
        if candidate_ref is None:
            raise ValueError("generated object candidate ref is required")
        return {
            "patch": patch_path,
            "candidate": Path(str(candidate_ref)),
            "object": refined_object_path,
            "mask": refined_mask_path,
            "composited": composited_path,
            "precomposited": precomposited_path,
            "blend_mask": core_mask_path,
            "core_mask": core_mask_path,
            "core_blend": core_patch_path,
            "final_polish": final_patch_path,
            "shadow": shadow_path,
            "variant_manifest": variant_manifest_path,
            "selected_bbox": placement_bbox,
            "placement_score": placement_score,
            "placement_variant_id": selected_variant["id"],
            "mask_source": self.mask_refine_backend or "layerdiffuse_alpha_first",
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

    def _validate_hidden_object_backends(self) -> None:
        required = {
            "relight_method": self.relight_method,
            "edge_blend_backend": self.edge_blend_backend,
            "core_blend_backend": self.core_blend_backend,
            "final_polish_backend": self.final_polish_backend,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise RuntimeError(
                "layerdiffuse_hidden_object_v1 requires configured backends: "
                + ", ".join(sorted(missing))
            )
        if self.mask_refine_backend == "rmbg_2_0" and not self.rmbg_model_id.strip():
            raise RuntimeError("layerdiffuse_hidden_object_v1 requires rmbg_model_id")
        if self.mask_refine_backend == "sam2" and not self.sam2_model_id.strip():
            raise RuntimeError("layerdiffuse_hidden_object_v1 requires sam2_model_id")
        if self.relight_method == "ic_light" and not self.ic_light_model_id.strip():
            raise RuntimeError("layerdiffuse_hidden_object_v1 requires ic_light_model_id")
        if self.edge_blend_backend and not self.edge_blend_model_id.strip():
            raise RuntimeError("layerdiffuse_hidden_object_v1 requires edge_blend_model_id")
        if self.core_blend_backend and not self.core_blend_model_id.strip():
            raise RuntimeError("layerdiffuse_hidden_object_v1 requires core_blend_model_id")
        if self.final_polish_backend and not self.final_polish_model_id.strip():
            raise RuntimeError("layerdiffuse_hidden_object_v1 requires final_polish_model_id")

    def _backend_runtime(self) -> BackendRuntime:
        return BackendRuntime(
            device=self.device,
            dtype=self.dtype,
            offload_mode=self.offload_mode,
            enable_attention_slicing=self.enable_attention_slicing,
            enable_vae_slicing=self.enable_vae_slicing,
            enable_vae_tiling=self.enable_vae_tiling,
            enable_xformers_memory_efficient_attention=self.enable_xformers_memory_efficient_attention,
            enable_fp8_layerwise_casting=self.enable_fp8_layerwise_casting,
            enable_channels_last=self.enable_channels_last,
        )

    def _refine_hidden_object_mask(self, *, image: Any, fallback_mask: Any) -> Any:
        if self.mask_refine_backend == "rmbg_2_0":
            if self._rmbg_refiner is None:
                self._rmbg_refiner = Rmbg20MaskRefiner(
                    model_id=self.rmbg_model_id,
                    runtime=self._backend_runtime(),
                )
            return self._rmbg_refiner.refine(image=image, fallback_mask=fallback_mask)
        if self.mask_refine_backend == "sam2":
            if self._sam2_refiner is None:
                self._sam2_refiner = Sam2MaskRefiner(
                    model_id=self.sam2_model_id,
                    runtime=self._backend_runtime(),
                )
            return self._sam2_refiner.refine(image=image, fallback_mask=fallback_mask)
        return fallback_mask

    def _get_object_blend_backend(self, backend_kind: str) -> DiffusionObjectBlendBackend:
        if backend_kind == "edge":
            if self._edge_blend_pipe is None:
                self._edge_blend_pipe = DiffusionObjectBlendBackend(
                    backend_name=self.edge_blend_backend,
                    model_id=self.edge_blend_model_id,
                    runtime=self._backend_runtime(),
                )
            return self._edge_blend_pipe
        if backend_kind == "core":
            if (
                self._core_blend_pipe is None
                and self._edge_blend_pipe is not None
                and self.core_blend_backend == self.edge_blend_backend
                and self.core_blend_model_id == self.edge_blend_model_id
            ):
                self._core_blend_pipe = self._edge_blend_pipe
            if self._core_blend_pipe is None:
                self._core_blend_pipe = DiffusionObjectBlendBackend(
                    backend_name=self.core_blend_backend,
                    model_id=self.core_blend_model_id,
                    runtime=self._backend_runtime(),
                )
            return self._core_blend_pipe
        if (
            self._final_polish_pipe is None
            and self._core_blend_pipe is not None
            and self.final_polish_backend == self.core_blend_backend
            and self.final_polish_model_id == self.core_blend_model_id
        ):
            self._final_polish_pipe = self._core_blend_pipe
        if self._final_polish_pipe is None:
            self._final_polish_pipe = DiffusionObjectBlendBackend(
                backend_name=self.final_polish_backend,
                model_id=self.final_polish_model_id,
                runtime=self._backend_runtime(),
            )
        return self._final_polish_pipe

    def _build_pre_match_variants(
        self,
        *,
        image: Any,
        bbox: tuple[int, int, int, int],
        object_image: Any,
        object_mask: Any,
    ) -> list[dict[str, Any]]:
        variants: list[dict[str, Any]] = []
        count = max(1, int(self.pre_match_variant_count))
        for index in range(count):
            fraction = 0.0 if count == 1 else index / float(count - 1)
            variant = self._transform_object_variant(
                image=image,
                bbox=bbox,
                object_image=object_image,
                object_mask=object_mask,
                scale_ratio=self._interpolate(self.pre_match_scale_ratio, fraction),
                rotation_deg=self._interpolate(self.pre_match_rotation_deg, fraction),
                saturation_mul=self._interpolate(self.pre_match_saturation_mul, fraction),
                contrast_mul=self._interpolate(self.pre_match_contrast_mul, fraction),
                sharpness_mul=self._interpolate(self.pre_match_sharpness_mul, fraction),
                index=index,
            )
            variants.append(variant)
        return variants

    def _select_best_variant(
        self,
        *,
        image: Any,
        bbox: tuple[int, int, int, int],
        variants: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], tuple[int, int, int, int], float]:
        best_variant = variants[0]
        best_bbox = bbox
        best_score = -1.0
        for variant in variants:
            placement_bbox, score = self._find_similarity_placement(
                image=image,
                patch=variant["object_image"],
                mask=variant["object_mask"],
                fallback_bbox=bbox,
            )
            variant["placement_bbox"] = placement_bbox
            variant["score"] = score
            if score > best_score:
                best_variant = variant
                best_bbox = placement_bbox
                best_score = score
        return best_variant, best_bbox, max(0.0, best_score)

    def _transform_object_variant(
        self,
        *,
        image: Any,
        bbox: tuple[int, int, int, int],
        object_image: Any,
        object_mask: Any,
        scale_ratio: float,
        rotation_deg: float,
        saturation_mul: float,
        contrast_mul: float,
        sharpness_mul: float,
        index: int,
    ) -> dict[str, Any]:
        from PIL import Image, ImageEnhance  # type: ignore

        canvas_side = max(128, int(self.final_context_size))
        rgba = object_image.convert("RGBA")
        mask = object_mask.convert("L")
        tight_bbox = mask.getbbox() or (0, 0, mask.width, mask.height)
        rgba = rgba.crop(tight_bbox)
        mask = mask.crop(tight_bbox)
        base_region = max(1, max(int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])))
        target_long_side = max(
            24,
            min(
                canvas_side - 8,
                max(
                    min(base_region, canvas_side - 8),
                    int(round(max(image.width, image.height) * float(scale_ratio))),
                ),
            ),
        )
        current_long_side = max(1, rgba.width, rgba.height)
        resize_scale = target_long_side / float(current_long_side)
        resized_size = (
            max(1, int(round(rgba.width * resize_scale))),
            max(1, int(round(rgba.height * resize_scale))),
        )
        rgba = rgba.resize(resized_size, Image.LANCZOS)
        mask = mask.resize(resized_size, Image.LANCZOS)
        rgba = ImageEnhance.Color(rgba).enhance(float(saturation_mul))
        rgba = ImageEnhance.Contrast(rgba).enhance(float(contrast_mul))
        rgba = ImageEnhance.Sharpness(rgba).enhance(float(sharpness_mul))
        rgba = rgba.rotate(float(rotation_deg), resample=Image.BICUBIC, expand=True)
        alpha = mask.rotate(float(rotation_deg), resample=Image.BICUBIC, expand=True)
        if alpha.getbbox() is None:
            alpha = mask
        rgba.putalpha(alpha)
        rgba = self._apply_relight_hint(rgba)
        canvas = Image.new("RGBA", (canvas_side, canvas_side), color=(0, 0, 0, 0))
        paste_left = max(0, (canvas_side - rgba.width) // 2)
        paste_top = max(0, (canvas_side - rgba.height) // 2)
        canvas.paste(rgba, (paste_left, paste_top), rgba)
        alpha_canvas = Image.new("L", (canvas_side, canvas_side), color=0)
        alpha_canvas.paste(alpha, (paste_left, paste_top), alpha)
        return {
            "id": f"variant-{index:02d}",
            "object_image": canvas,
            "object_mask": alpha_canvas,
            "scale_ratio": scale_ratio,
            "rotation_deg": rotation_deg,
            "saturation_mul": saturation_mul,
            "contrast_mul": contrast_mul,
            "sharpness_mul": sharpness_mul,
            "target_long_side": min(target_long_side, base_region),
        }

    def _apply_relight_hint(self, image: Any) -> Any:
        from PIL import ImageEnhance  # type: ignore

        if self.relight_method == "ic_light":
            if self._ic_light_relighter is None:
                self._ic_light_relighter = IcLightRelighter(
                    model_id=self.ic_light_model_id,
                    runtime=self._backend_runtime(),
                )
            return self._ic_light_relighter.relight(
                rgba_object=image,
                prompt="hidden object harmonized lighting",
                negative_prompt=self.default_negative_prompt,
                strength=0.18,
            )
        image = ImageEnhance.Brightness(image).enhance(0.96)
        return ImageEnhance.Contrast(image).enhance(0.97)

    def _opaque_composite_object(
        self,
        *,
        image: Any,
        object_image: Any,
        object_mask: Any,
        target_bbox: tuple[int, int, int, int],
    ) -> tuple[Any, Any]:
        from PIL import ImageFilter  # type: ignore

        opaque = object_image.copy().convert("RGBA")
        opaque.putalpha(object_mask.convert("L"))
        if self.composite_feather_px > 0:
            feathered = object_mask.convert("L").filter(
                ImageFilter.GaussianBlur(radius=max(1, int(self.composite_feather_px)))
            )
        else:
            feathered = object_mask.convert("L")
        opaque.putalpha(feathered)
        composited = apply_alpha_patch_with_opacity(
            image,
            opaque,
            target_bbox,
            opacity=self.overlay_alpha,
        )
        return composited, feathered

    def _run_object_blend_pass(
        self,
        *,
        handle: ModelHandle,
        source_image: Any,
        target_bbox: tuple[int, int, int, int],
        localized_mask: Any,
        prompt: str,
        negative_prompt: str,
        strength: float,
        num_inference_steps: int,
        guidance_scale: float,
        backend_kind: str,
    ) -> dict[str, Any]:
        crop_bbox_with_padding = self._build_context_crop_bbox(
            image=source_image,
            target_bbox=target_bbox,
        )
        original_patch = crop_bbox(source_image, crop_bbox_with_padding)
        blend_mask = self._localize_object_mask(
            crop_bbox=crop_bbox_with_padding,
            target_bbox=target_bbox,
            working_size=original_patch.size,
            object_mask=localized_mask,
        )
        backend = self._get_object_blend_backend(backend_kind)
        generated_patch = backend.generate(
            image=original_patch,
            mask=blend_mask,
            prompt=prompt,
            negative_prompt=negative_prompt,
            strength=float(strength),
            num_inference_steps=int(num_inference_steps),
            guidance_scale=float(guidance_scale),
        )
        generated_patch = normalize_generated_patch(generated_patch, original_patch.size)
        composited = self._apply_patch_to_crop(
            image=source_image,
            patch=generated_patch,
            crop_bbox=crop_bbox_with_padding,
        )
        return {
            "generated_patch": generated_patch,
            "composited": composited,
            "blend_mask": blend_mask,
        }

    def _apply_direct_shadow(
        self,
        *,
        image: Any,
        object_mask: Any,
        target_bbox: tuple[int, int, int, int],
    ) -> Any:
        from PIL import Image, ImageFilter  # type: ignore

        crop_bbox_with_padding = self._build_context_crop_bbox(
            image=image,
            target_bbox=target_bbox,
        )
        localized_mask = self._localize_object_mask(
            crop_bbox=crop_bbox_with_padding,
            target_bbox=target_bbox,
            working_size=(crop_bbox_with_padding[2] - crop_bbox_with_padding[0], crop_bbox_with_padding[3] - crop_bbox_with_padding[1]),
            object_mask=object_mask,
        )
        shadow_mask = localized_mask.filter(
            ImageFilter.GaussianBlur(radius=max(1, int(self.shadow_blur_px)))
        )
        shadow_mask = shadow_mask.point(
            lambda value: int(max(0, min(255, value * float(self.shadow_opacity))))
        )
        crop = crop_bbox(image, crop_bbox_with_padding).convert("RGBA")
        shadow = Image.new("RGBA", crop.size, color=(0, 0, 0, 0))
        shadow.paste(
            Image.new("RGBA", crop.size, color=(0, 0, 0, 255)),
            (0, 0),
            shadow_mask,
        )
        composited_crop = Image.alpha_composite(crop, shadow)
        return self._apply_patch_to_crop(
            image=image,
            patch=composited_crop.convert("RGB"),
            crop_bbox=crop_bbox_with_padding,
        )

    def _interpolate(self, bounds: tuple[float, float], fraction: float) -> float:
        low, high = bounds
        return float(low + (high - low) * fraction)

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
        crop_bbox_with_padding = expand_bbox(
            self._build_context_crop_bbox(
                image=source_image,
                target_bbox=target_bbox,
            ),
            padding=0,
            width=source_image.width,
            height=source_image.height,
        )
        original_patch = crop_bbox(source_image, crop_bbox_with_padding)
        working_patch = original_patch
        working_size = original_patch.size
        blend_mask = self._build_blend_mask(
            crop_bbox=crop_bbox_with_padding,
            target_bbox=target_bbox,
            working_size=working_size,
            object_mask=object_mask,
        )
        generated_patch = self._generate_image(
            handle=handle,
            image=working_patch,
            mask=blend_mask,
            prompt=(
                "blend the pasted object naturally into the surrounding scene "
                "while preserving the object's identity and silhouette"
            ),
            negative_prompt=request.negative_prompt or self.default_negative_prompt,
            strength=float(self.final_inpaint_strength or 0.18),
            num_inference_steps=int(self.final_inpaint_steps or 6),
            guidance_scale=float(self.final_inpaint_guidance_scale or 2.0),
            mask_blur=int(self.final_mask_blur or request.mask_blur or self.mask_blur),
            inpaint_only_masked=True,
            padding_mask_crop=None,
        )
        generated_patch = normalize_generated_patch(generated_patch, working_size)
        composited = self._apply_patch_to_crop(
            image=source_image,
            patch=generated_patch,
            crop_bbox=crop_bbox_with_padding,
        )
        return {
            "generated_patch": generated_patch,
            "composited": composited,
            "blend_mask": blend_mask,
        }

    def _build_blend_mask(
        self,
        *,
        crop_bbox: tuple[int, int, int, int],
        target_bbox: tuple[int, int, int, int],
        working_size: tuple[int, int],
        object_mask: Any,
    ) -> Any:
        from PIL import ImageFilter  # type: ignore

        localized_mask = self._localize_object_mask(
            crop_bbox=crop_bbox,
            target_bbox=target_bbox,
            working_size=working_size,
            object_mask=object_mask,
        )
        localized_mask = localized_mask.filter(
            ImageFilter.GaussianBlur(radius=max(1, int(self.final_mask_blur or 4)))
        )
        return localized_mask

    def _build_context_crop_bbox(
        self,
        *,
        image: Any,
        target_bbox: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        crop_size = min(
            max(1, int(self.final_context_size)),
            image.width,
            image.height,
        )
        target_left, target_top, target_right, target_bottom = target_bbox
        center_x = (target_left + target_right) / 2.0
        center_y = (target_top + target_bottom) / 2.0
        left = int(round(center_x - crop_size / 2.0))
        top = int(round(center_y - crop_size / 2.0))
        left = min(max(0, left), max(0, image.width - crop_size))
        top = min(max(0, top), max(0, image.height - crop_size))
        return (left, top, left + crop_size, top + crop_size)

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

        tight_bbox = mask.convert("L").getbbox()
        if tight_bbox is not None:
            patch = patch.crop(tight_bbox)
            mask = mask.crop(tight_bbox)
        left, top, right, bottom = fallback_bbox
        region_w = patch.width
        region_h = patch.height
        if region_w < 1 or region_h < 1:
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
