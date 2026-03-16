from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .pipeline_memory import OffloadMode, configure_diffusers_pipeline
from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
    validate_diffusers_runtime,
)
from .runtime_cleanup import clear_model_runtime

logger = get_logger("discoverex.models.pixart_background")


class PixArtSigmaBackgroundGenerationModel:
    def __init__(
        self,
        model_id: str = "PixArt-alpha/PixArt-Sigma-XL-2-1024-MS",
        revision: str = "main",
        device: str = "cuda",
        dtype: str = "float16",
        precision: str = "fp16",
        batch_size: int = 1,
        seed: int | None = None,
        strict_runtime: bool = False,
        offload_mode: OffloadMode = "model",
        enable_attention_slicing: bool = True,
        enable_vae_slicing: bool = True,
        enable_vae_tiling: bool = True,
        enable_xformers_memory_efficient_attention: bool = True,
        enable_fp8_layerwise_casting: bool = False,
        enable_channels_last: bool = True,
        detail_model_id: str = "stabilityai/stable-diffusion-xl-refiner-1.0",
        default_prompt: str = "cinematic hidden object puzzle background",
        default_negative_prompt: str = (
            "blurry, low quality, extra fingers, bad anatomy, "
            "jpeg artifacts, text artifacts"
        ),
        default_num_inference_steps: int = 20,
        default_guidance_scale: float = 5.0,
        canvas_scale_factor: float = 2.0,
        detail_num_inference_steps: int = 24,
        detail_guidance_scale: float = 4.0,
        detail_strength: float = 0.35,
        tile_size: int = 512,
        tile_overlap: int = 64,
        enable_highres_extension: bool = False,
        extension_scale_factor: float = 1.5,
        extension_num_inference_steps: int = 20,
        extension_guidance_scale: float = 3.8,
        extension_strength: float = 0.30,
        text_encoder_8bit: bool = False,
        text_encoder_offload: bool = True,
        prompt_embedding_cache: bool = True,
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
        self.detail_model_id = detail_model_id
        self.default_prompt = default_prompt
        self.default_negative_prompt = default_negative_prompt
        self.default_num_inference_steps = default_num_inference_steps
        self.default_guidance_scale = default_guidance_scale
        self.canvas_scale_factor = canvas_scale_factor
        self.detail_num_inference_steps = detail_num_inference_steps
        self.detail_guidance_scale = detail_guidance_scale
        self.detail_strength = detail_strength
        self.tile_size = tile_size
        self.tile_overlap = tile_overlap
        self.enable_highres_extension = enable_highres_extension
        self.extension_scale_factor = extension_scale_factor
        self.extension_num_inference_steps = extension_num_inference_steps
        self.extension_guidance_scale = extension_guidance_scale
        self.extension_strength = extension_strength
        self.text_encoder_8bit = text_encoder_8bit
        self.text_encoder_offload = text_encoder_offload
        self.prompt_embedding_cache = prompt_embedding_cache
        self._base_pipe: Any | None = None
        self._detail_pipe: Any | None = None

    def load(self, model_ref_or_version: str) -> ModelHandle:
        logger.info(
            "loading pixart background generation model model_id=%s revision=%s requested_device=%s",
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
            name="background_generation_model",
            version=model_ref_or_version,
            runtime="pixart_sigma_text2image",
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

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction:
        started = perf_counter()
        output_path = request.params.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")
        output = Path(output_path)
        if request.mode == "canvas_upscale":
            path = self._predict_canvas_upscale(request=request, output_path=output)
            logger.info(
                "pixart canvas upscale image saved path=%s duration=%s",
                path,
                format_seconds(started),
            )
            return {"fx": "background_canvas_upscale", "output_path": str(path)}
        if request.mode == "detail_reconstruct":
            path = self._predict_detail_reconstruct(
                handle=handle,
                request=request,
                output_path=output,
            )
            logger.info(
                "pixart detail reconstruction image saved path=%s duration=%s",
                path,
                format_seconds(started),
            )
            return {"fx": "background_detail_reconstruct", "output_path": str(path)}
        if request.mode == "hires_fix":
            path = self._predict_hires_fix(handle=handle, request=request, output_path=output)
            logger.info(
                "pixart hires-fix image saved path=%s duration=%s",
                path,
                format_seconds(started),
            )
            return {"fx": "background_hires_fix", "output_path": str(path)}
        path = self._predict_background(handle=handle, request=request, output_path=output)
        logger.info(
            "pixart background image saved path=%s duration=%s",
            path,
            format_seconds(started),
        )
        return {"fx": request.mode or "background_generation", "output_path": str(path)}

    def _predict_background(
        self,
        *,
        handle: ModelHandle,
        request: FxRequest,
        output_path: Path,
    ) -> Path:
        width = as_positive_int(request.params.get("width"), fallback=1024)
        height = as_positive_int(request.params.get("height"), fallback=1024)
        seed = as_int_or_none(request.params.get("seed"), fallback=self.seed)
        prompt = as_str(request.params.get("prompt"), fallback=self.default_prompt)
        negative_prompt = as_str(
            request.params.get("negative_prompt"),
            fallback=self.default_negative_prompt,
        )
        num_inference_steps = as_positive_int(
            request.params.get("num_inference_steps"),
            fallback=self.default_num_inference_steps,
        )
        guidance_scale = as_float(
            request.params.get("guidance_scale"),
            fallback=self.default_guidance_scale,
        )
        image = self._generate_base_image(
            handle=handle,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        return output_path

    def _predict_hires_fix(
        self,
        *,
        handle: ModelHandle,
        request: FxRequest,
        output_path: Path,
    ) -> Path:
        canvas_output = output_path.with_suffix(".canvas.png")
        canvas_path = self._predict_canvas_upscale(
            request=request,
            output_path=canvas_output,
        )
        detail_request = request.model_copy(
            update={
                "mode": "detail_reconstruct",
                "image_ref": str(canvas_path),
                "params": {
                    **request.params,
                    "image_ref": str(canvas_path),
                    "output_path": str(output_path),
                },
            }
        )
        return self._predict_detail_reconstruct(
            handle=handle,
            request=detail_request,
            output_path=output_path,
        )

    def _predict_canvas_upscale(
        self,
        *,
        request: FxRequest,
        output_path: Path,
    ) -> Path:
        from PIL import Image  # type: ignore

        image_ref = request.params.get("image_ref")
        if not isinstance(image_ref, (str, Path)) or not str(image_ref):
            raise ValueError("FxRequest.params.image_ref is required for canvas_upscale")
        source_path = Path(str(image_ref))
        width = as_positive_int(request.params.get("width"), fallback=2048)
        height = as_positive_int(request.params.get("height"), fallback=2048)
        canvas_scale_factor = as_float(
            request.params.get("canvas_scale_factor"),
            fallback=self.canvas_scale_factor,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path).convert("RGB") as image:
            canvas = self._upscale_canvas(
                image=image,
                width=width,
                height=height,
                canvas_scale_factor=canvas_scale_factor,
            )
            canvas.save(output_path)
        return output_path

    def _predict_detail_reconstruct(
        self,
        *,
        handle: ModelHandle,
        request: FxRequest,
        output_path: Path,
    ) -> Path:
        from PIL import Image  # type: ignore

        image_ref = request.params.get("image_ref")
        if not isinstance(image_ref, (str, Path)) or not str(image_ref):
            raise ValueError(
                "FxRequest.params.image_ref is required for detail_reconstruct"
            )
        source_path = Path(str(image_ref))
        seed = as_int_or_none(request.params.get("seed"), fallback=self.seed)
        prompt = as_str(request.params.get("prompt"), fallback=self.default_prompt)
        negative_prompt = as_str(
            request.params.get("negative_prompt"),
            fallback=self.default_negative_prompt,
        )
        detail_steps = as_positive_int(
            request.params.get("detail_num_inference_steps"),
            fallback=as_positive_int(
                request.params.get("num_inference_steps"),
                fallback=self.detail_num_inference_steps,
            ),
        )
        detail_guidance = as_float(
            request.params.get("detail_guidance_scale"),
            fallback=as_float(
                request.params.get("guidance_scale"),
                fallback=self.detail_guidance_scale,
            ),
        )
        detail_strength = as_float(
            request.params.get("detail_strength"),
            fallback=as_float(
                request.params.get("refiner_strength"),
                fallback=self.detail_strength,
            ),
        )
        enable_extension = bool(
            request.params.get("enable_highres_extension", self.enable_highres_extension)
        )
        extension_scale_factor = as_float(
            request.params.get("extension_scale_factor"),
            fallback=self.extension_scale_factor,
        )
        extension_steps = as_positive_int(
            request.params.get("extension_num_inference_steps"),
            fallback=self.extension_num_inference_steps,
        )
        extension_guidance = as_float(
            request.params.get("extension_guidance_scale"),
            fallback=self.extension_guidance_scale,
        )
        extension_strength = as_float(
            request.params.get("extension_strength"),
            fallback=self.extension_strength,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path).convert("RGB") as image:
            refined = self._reconstruct_details(
                handle=handle,
                image=image,
                prompt=prompt,
                negative_prompt=negative_prompt,
                seed=seed,
                num_inference_steps=detail_steps,
                guidance_scale=detail_guidance,
                strength=detail_strength,
            )
            if enable_extension:
                extension_w = max(1, int(round(refined.width * extension_scale_factor)))
                extension_h = max(1, int(round(refined.height * extension_scale_factor)))
                extended = refined.resize(
                    (extension_w, extension_h),
                    Image.Resampling.LANCZOS,
                )
                refined = self._reconstruct_details(
                    handle=handle,
                    image=extended,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    seed=seed,
                    num_inference_steps=extension_steps,
                    guidance_scale=extension_guidance,
                    strength=extension_strength,
                )
            refined.save(output_path)
        return output_path

    def _generate_base_image(
        self,
        *,
        handle: ModelHandle,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: int | None,
        num_inference_steps: int,
        guidance_scale: float,
    ) -> Any:
        try:
            import torch  # type: ignore
        except Exception as exc:
            raise RuntimeError("torch runtime unavailable") from exc
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        pipe = self._load_base_pipe(handle)
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            generator=generator,
        )
        images = getattr(result, "images", None)
        if not images:
            raise RuntimeError("pixart pipeline returned no images")
        return images[0]

    def _upscale_canvas(
        self,
        *,
        image: Any,
        width: int,
        height: int,
        canvas_scale_factor: float,
    ) -> Any:
        from PIL import Image  # type: ignore

        if width <= 0 or height <= 0:
            target_w = max(1, int(round(image.width * canvas_scale_factor)))
            target_h = max(1, int(round(image.height * canvas_scale_factor)))
        else:
            target_w = width
            target_h = height
        return image.resize((target_w, target_h), Image.Resampling.LANCZOS)

    def _reconstruct_details(
        self,
        *,
        handle: ModelHandle,
        image: Any,
        prompt: str,
        negative_prompt: str,
        seed: int | None,
        num_inference_steps: int,
        guidance_scale: float,
        strength: float,
    ) -> Any:
        if not self.detail_model_id:
            return image
        return self._refine_tiled(
            handle=handle,
            image=image,
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            strength=strength,
        )

    def _refine_tiled(
        self,
        *,
        handle: ModelHandle,
        image: Any,
        prompt: str,
        negative_prompt: str,
        seed: int | None,
        num_inference_steps: int,
        guidance_scale: float,
        strength: float,
    ) -> Any:
        from PIL import Image  # type: ignore

        try:
            import numpy as np
            import torch  # type: ignore
        except Exception as exc:
            raise RuntimeError("pixart tiled refinement runtime unavailable") from exc

        pipe = self._load_detail_pipe(handle)
        tile_size = max(64, int(self.tile_size))
        overlap = max(0, min(int(self.tile_overlap), tile_size // 2))
        step = max(1, tile_size - overlap)
        canvas = np.zeros((image.height, image.width, 3), dtype=np.float32)
        weights = np.zeros((image.height, image.width, 1), dtype=np.float32)
        tile_index = 0
        for top in self._tile_positions(image.height, tile_size, step):
            for left in self._tile_positions(image.width, tile_size, step):
                tile = image.crop((left, top, left + tile_size, top + tile_size))
                generator = None
                if seed is not None:
                    generator = torch.Generator(device="cpu").manual_seed(
                        seed + tile_index
                    )
                result = pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    image=tile,
                    strength=strength,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                )
                images = getattr(result, "images", None)
                refined_tile = images[0] if images else tile
                tile_arr = np.asarray(refined_tile.convert("RGB"), dtype=np.float32)
                weight = self._build_weight_map(
                    width=tile_arr.shape[1],
                    height=tile_arr.shape[0],
                    feather=max(8, overlap // 2),
                )
                bottom = min(image.height, top + tile_arr.shape[0])
                right = min(image.width, left + tile_arr.shape[1])
                tile_crop = tile_arr[: bottom - top, : right - left, :]
                weight_crop = weight[: bottom - top, : right - left, :]
                canvas[top:bottom, left:right, :] += tile_crop * weight_crop
                weights[top:bottom, left:right, :] += weight_crop
                tile_index += 1
        weights = np.maximum(weights, 1e-6)
        merged = np.clip(canvas / weights, 0.0, 255.0).astype("uint8")
        return Image.fromarray(merged, mode="RGB")

    def _tile_positions(self, length: int, tile_size: int, step: int) -> list[int]:
        if length <= tile_size:
            return [0]
        positions = list(range(0, max(1, length - tile_size + 1), step))
        last = max(0, length - tile_size)
        if not positions or positions[-1] != last:
            positions.append(last)
        return positions

    def _build_weight_map(self, *, width: int, height: int, feather: int) -> Any:
        import numpy as np

        feather = max(1, min(feather, width // 2, height // 2))
        x = np.ones(width, dtype=np.float32)
        y = np.ones(height, dtype=np.float32)
        ramp_x = np.linspace(0.0, 1.0, feather, dtype=np.float32)
        ramp_y = np.linspace(0.0, 1.0, feather, dtype=np.float32)
        x[:feather] = ramp_x
        x[-feather:] = ramp_x[::-1]
        y[:feather] = ramp_y
        y[-feather:] = ramp_y[::-1]
        weight = np.outer(y, x)
        return weight[:, :, None]

    def _load_base_pipe(self, handle: ModelHandle) -> Any:
        if self._base_pipe is not None:
            return self._base_pipe
        try:
            import torch  # type: ignore
            from diffusers import (  # type: ignore
                DPMSolverMultistepScheduler,
                PixArtSigmaPipeline,
            )
        except Exception as exc:
            runtime = resolve_runtime()
            validate_diffusers_runtime(runtime)
            raise RuntimeError(
                "diffusers pixart runtime unavailable. Install compatible ml-gpu dependencies."
            ) from exc
        torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        pipe = PixArtSigmaPipeline.from_pretrained(
            self.model_id,
            revision=self.revision,
            torch_dtype=torch_dtype,
        )
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config,
            use_karras_sigmas=True,
            algorithm_type="dpmsolver++",
            solver_order=2,
        )
        self._base_pipe = configure_diffusers_pipeline(
            pipe,
            handle=handle,
            offload_mode=self.offload_mode,
            enable_attention_slicing=self.enable_attention_slicing,
            enable_vae_slicing=self.enable_vae_slicing,
            enable_vae_tiling=self.enable_vae_tiling,
            enable_xformers_memory_efficient_attention=self.enable_xformers_memory_efficient_attention,
            enable_fp8_layerwise_casting=self.enable_fp8_layerwise_casting,
            enable_channels_last=self.enable_channels_last,
        )
        return self._base_pipe

    def _load_detail_pipe(self, handle: ModelHandle) -> Any:
        if self._detail_pipe is not None:
            return self._detail_pipe
        try:
            import torch  # type: ignore
            from diffusers import (  # type: ignore
                AutoPipelineForImage2Image,
                DPMSolverMultistepScheduler,
            )
        except Exception as exc:
            runtime = resolve_runtime()
            validate_diffusers_runtime(runtime)
            raise RuntimeError(
                "diffusers image-to-image runtime unavailable. Install compatible ml-gpu dependencies."
            ) from exc
        torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        pipe = AutoPipelineForImage2Image.from_pretrained(
            self.detail_model_id,
            torch_dtype=torch_dtype,
        )
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config,
            algorithm_type="dpmsolver++",
            solver_order=2,
        )
        self._detail_pipe = configure_diffusers_pipeline(
            pipe,
            handle=handle,
            offload_mode=self.offload_mode,
            enable_attention_slicing=self.enable_attention_slicing,
            enable_vae_slicing=self.enable_vae_slicing,
            enable_vae_tiling=self.enable_vae_tiling,
            enable_xformers_memory_efficient_attention=self.enable_xformers_memory_efficient_attention,
            enable_fp8_layerwise_casting=self.enable_fp8_layerwise_casting,
            enable_channels_last=self.enable_channels_last,
        )
        return self._detail_pipe

    def unload(self) -> None:
        clear_model_runtime(self._base_pipe, self._detail_pipe)
        self._base_pipe = None
        self._detail_pipe = None
