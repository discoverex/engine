from __future__ import annotations

from time import perf_counter
from typing import Any

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .background.pixart.base import generate_base_image
from .background.pixart.detail import reconstruct_details
from .background.pixart.load import load_base_pipe, load_detail_pipe
from .background.pixart.params import background_params, canvas_params, detail_params
from .background.pixart.service import (
    predict_canvas_upscale,
    predict_detail_reconstruct,
    predict_hires_fix,
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
        default_negative_prompt: str = "blurry, low quality, extra fingers, bad anatomy, jpeg artifacts, text artifacts",
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
        self.enable_xformers_memory_efficient_attention = enable_xformers_memory_efficient_attention
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
        runtime = resolve_runtime()
        validate_diffusers_runtime(runtime)
        selected_device = resolve_device(self.device, runtime.torch)
        selected_dtype = str(normalize_dtype(self.dtype, runtime.torch))
        if self.strict_runtime and not runtime.available:
            raise RuntimeError(f"torch/transformers runtime unavailable: {runtime.reason}")
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
        path: Any
        fx_name: str
        if request.mode == "canvas_upscale":
            canvas = canvas_params(request, self)
            path = self._predict_canvas_upscale(*canvas)
            fx_name = "background_canvas_upscale"
        elif request.mode == "detail_reconstruct":
            detail = detail_params(request, self)
            path = self._predict_detail_reconstruct(handle=handle, params=detail)
            fx_name = "background_detail_reconstruct"
        elif request.mode == "hires_fix":
            detail = detail_params(request, self)
            path = self._predict_hires_fix(handle=handle, params=detail)
            fx_name = "background_hires_fix"
        else:
            background = background_params(request, self)
            image = self._generate_base_image(handle=handle, **background.__dict__)
            background.output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(background.output_path)
            path = background.output_path
            fx_name = request.mode or "background_generation"
        logger.info("pixart background image saved path=%s duration=%s", path, format_seconds(started))
        return {"fx": fx_name, "output_path": str(path)}

    def _predict_canvas_upscale(self, output_path: Any, source_path: Any, width: int, height: int, canvas_scale_factor: float) -> Any:
        return predict_canvas_upscale(output_path=output_path, source_path=source_path, width=width, height=height, canvas_scale_factor=canvas_scale_factor)

    def _predict_detail_reconstruct(self, *, handle: ModelHandle, params: Any) -> Any:
        return predict_detail_reconstruct(model=self, handle=handle, params=params)

    def _predict_hires_fix(self, *, handle: ModelHandle, params: Any) -> Any:
        return predict_hires_fix(model=self, handle=handle, params=params)

    def _generate_base_image(self, **kwargs: Any) -> Any:
        kwargs.pop("output_path", None)
        return generate_base_image(model=self, **kwargs)

    def _reconstruct_details(self, **kwargs: Any) -> Any:
        return reconstruct_details(model=self, **kwargs)

    def _load_base_pipe(self, handle: ModelHandle) -> Any:
        if self._base_pipe is None:
            self._base_pipe = load_base_pipe(model=self, handle=handle)
        return self._base_pipe

    def _load_detail_pipe(self, handle: ModelHandle) -> Any:
        if self._detail_pipe is None:
            self._detail_pipe = load_detail_pipe(model=self, handle=handle)
        return self._detail_pipe

    def unload(self) -> None:
        clear_model_runtime(self._base_pipe, self._detail_pipe)
        self._base_pipe = None
        self._detail_pipe = None
