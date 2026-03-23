from __future__ import annotations

# mypy: ignore-errors
from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .objects.layerdiffuse.cache import resolve_shared_cache_dir
from .objects.layerdiffuse.generate import (
    LayerDiffuseGenerationResult,
    generate_rgba,
    generate_rgba_batch,
)
from .objects.layerdiffuse.load import load_pipeline
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

logger = get_logger("discoverex.models.layerdiffuse_object")


def _stdout_debug(message: str) -> None:
    print(f"[discoverex-debug] {message}", flush=True)


class LayerDiffuseObjectGenerationModel:
    def __init__(
        self,
        model_id: str = "SG161222/RealVisXL_V5.0",
        pipeline_variant: str = "",
        weights_repo: str = "",
        transparent_decoder_weight_name: str = "",
        attn_weight_name: str = "",
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
        sampler: str = "dpmpp_sde_karras",
        default_prompt: str = "isolated single object on a transparent background",
        default_negative_prompt: str = "busy scene, environment, multiple objects, floor, wall, clutter, blurry, low quality, artifact",
        default_num_inference_steps: int = 30,
        default_guidance_scale: float = 5.0,
        weights_cache_dir: str = ".cache/layerdiffuse",
        model_cache_dir: str = "",
        hf_home: str = "",
        model_cache_policy: str = "local_first",
        allow_remote_model_fetch: bool = True,
        required_local_snapshot: str = "",
        prefetch_model_on_load: bool = False,
    ) -> None:
        self.model_id = model_id
        self.pipeline_variant = pipeline_variant
        self.weights_repo = weights_repo
        self.transparent_decoder_weight_name = transparent_decoder_weight_name
        self.attn_weight_name = attn_weight_name
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
        self.sampler = sampler
        self.default_prompt = default_prompt
        self.default_negative_prompt = default_negative_prompt
        self.default_num_inference_steps = default_num_inference_steps
        self.default_guidance_scale = default_guidance_scale
        self.weights_cache_dir = str(
            resolve_shared_cache_dir(
                weights_cache_dir,
                model_cache_dir=model_cache_dir,
                hf_home=hf_home,
            )
        )
        self.model_cache_dir = model_cache_dir
        self.hf_home = hf_home
        self.model_cache_policy = model_cache_policy
        self.allow_remote_model_fetch = allow_remote_model_fetch
        self.required_local_snapshot = required_local_snapshot
        self.prefetch_model_on_load = prefetch_model_on_load
        self._pipe: Any | None = None
        self._transparent_decoder: Any | None = None
        self._layerdiffuse_applied = False

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
        _stdout_debug(
            "object_model_load "
            f"model_id={self.model_id} sampler={self.sampler} "
            f"requested_offload_mode={self.offload_mode} "
            f"dtype={self.dtype} precision={self.precision} "
            f"batch_size={self.batch_size} seed={self.seed}"
        )
        return ModelHandle(
            name="object_generation_model",
            version=model_ref_or_version,
            runtime="layerdiffuse_object_generation",
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
        output_path_value = as_str(request.params.get("output_path"), fallback="")
        if not output_path_value:
            raise ValueError("FxRequest.params.output_path is required")
        path = Path(output_path_value)
        preview_path_value = as_str(request.params.get("preview_output_path"), fallback="")
        alpha_path_value = as_str(request.params.get("alpha_output_path"), fallback="")
        visualization_path_value = as_str(
            request.params.get("visualization_output_path"),
            fallback="",
        )
        preview_path = Path(preview_path_value) if preview_path_value else None
        alpha_path = Path(alpha_path_value) if alpha_path_value else None
        visualization_path = (
            Path(visualization_path_value) if visualization_path_value else None
        )
        image = self._generate_rgba(
            handle=handle,
            prompt=as_str(request.params.get("prompt"), fallback=self.default_prompt),
            negative_prompt=as_str(request.params.get("negative_prompt"), fallback=self.default_negative_prompt),
            width=as_positive_int(request.params.get("width"), fallback=512),
            height=as_positive_int(request.params.get("height"), fallback=512),
            seed=as_int_or_none(request.params.get("seed"), fallback=self.seed),
            num_inference_steps=as_positive_int(request.params.get("num_inference_steps"), fallback=self.default_num_inference_steps),
            guidance_scale=as_float(request.params.get("guidance_scale"), fallback=self.default_guidance_scale),
            max_vram_gb=(
                as_float(request.params.get("max_vram_gb"), fallback=0.0)
                if request.params.get("max_vram_gb") is not None
                else None
            ),
        )
        if not isinstance(image, LayerDiffuseGenerationResult):
            rgba = image.convert("RGBA")
            image = LayerDiffuseGenerationResult(
                preview_rgb=rgba.convert("RGB"),
                transparent_rgba=rgba,
                alpha_mask=rgba.getchannel("A"),
                visualization_rgb=rgba.convert("RGB"),
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        image.transparent_rgba.save(path)
        if preview_path is not None:
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            image.preview_rgb.save(preview_path)
        if alpha_path is not None:
            alpha_path.parent.mkdir(parents=True, exist_ok=True)
            image.alpha_mask.save(alpha_path)
        if visualization_path is not None:
            visualization_path.parent.mkdir(parents=True, exist_ok=True)
            image.visualization_rgb.save(visualization_path)
        logger.info("layerdiffuse object image saved path=%s duration=%s", path, format_seconds(started))
        return {
            "fx": request.mode or "object_generation",
            "output_path": str(path),
            "preview_output_path": str(preview_path) if preview_path is not None else "",
            "alpha_output_path": str(alpha_path) if alpha_path is not None else "",
            "visualization_output_path": (
                str(visualization_path) if visualization_path is not None else ""
            ),
        }

    def predict_batch(self, handle: ModelHandle, request: FxRequest) -> FxPrediction:
        started = perf_counter()
        output_paths = [Path(str(path)) for path in list(request.params.get("output_paths") or [])]
        preview_output_paths = [
            Path(str(path)) for path in list(request.params.get("preview_output_paths") or [])
        ]
        alpha_output_paths = [
            Path(str(path)) for path in list(request.params.get("alpha_output_paths") or [])
        ]
        visualization_output_paths = [
            Path(str(path))
            for path in list(request.params.get("visualization_output_paths") or [])
        ]
        prompts = [str(prompt) for prompt in list(request.params.get("prompts") or [])]
        if not output_paths:
            raise ValueError("FxRequest.params.output_paths is required")
        if len(output_paths) != len(prompts):
            raise ValueError("output_paths and prompts must have the same length")
        if preview_output_paths and len(preview_output_paths) != len(output_paths):
            raise ValueError("preview_output_paths and output_paths must have the same length")
        if alpha_output_paths and len(alpha_output_paths) != len(output_paths):
            raise ValueError("alpha_output_paths and output_paths must have the same length")
        if visualization_output_paths and len(visualization_output_paths) != len(output_paths):
            raise ValueError("visualization_output_paths and output_paths must have the same length")
        negative_prompt = as_str(
            request.params.get("negative_prompt"),
            fallback=self.default_negative_prompt,
        )
        images = generate_rgba_batch(
            model=self,
            handle=handle,
            prompts=prompts,
            negative_prompts=[negative_prompt] * len(prompts),
            width=as_positive_int(request.params.get("width"), fallback=512),
            height=as_positive_int(request.params.get("height"), fallback=512),
            seed=as_int_or_none(request.params.get("seed"), fallback=self.seed),
            num_inference_steps=as_positive_int(
                request.params.get("num_inference_steps"),
                fallback=self.default_num_inference_steps,
            ),
            guidance_scale=as_float(
                request.params.get("guidance_scale"),
                fallback=self.default_guidance_scale,
            ),
            max_vram_gb=(
                as_float(request.params.get("max_vram_gb"), fallback=0.0)
                if request.params.get("max_vram_gb") is not None
                else None
            ),
        )
        saved_paths: list[str] = []
        preview_saved_paths: list[str] = []
        alpha_saved_paths: list[str] = []
        visualization_saved_paths: list[str] = []
        for index, (path, image) in enumerate(zip(output_paths, images, strict=True)):
            path.parent.mkdir(parents=True, exist_ok=True)
            image.transparent_rgba.save(path)
            saved_paths.append(str(path))
            if preview_output_paths:
                preview_path = preview_output_paths[index]
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                image.preview_rgb.save(preview_path)
                preview_saved_paths.append(str(preview_path))
            if alpha_output_paths:
                alpha_path = alpha_output_paths[index]
                alpha_path.parent.mkdir(parents=True, exist_ok=True)
                image.alpha_mask.save(alpha_path)
                alpha_saved_paths.append(str(alpha_path))
            if visualization_output_paths:
                visualization_path = visualization_output_paths[index]
                visualization_path.parent.mkdir(parents=True, exist_ok=True)
                image.visualization_rgb.save(visualization_path)
                visualization_saved_paths.append(str(visualization_path))
        logger.info(
            "layerdiffuse object batch saved count=%s duration=%s",
            len(saved_paths),
            format_seconds(started),
        )
        return {
            "fx": request.mode or "object_generation",
            "output_paths": saved_paths,
            "preview_output_paths": preview_saved_paths,
            "alpha_output_paths": alpha_saved_paths,
            "visualization_output_paths": visualization_saved_paths,
        }

    def _generate_rgba(self, **kwargs: Any) -> Any:
        return generate_rgba(model=self, **kwargs)

    def _load_pipeline(self, handle: ModelHandle) -> Any:
        if self._pipe is None:
            self._pipe = load_pipeline(model=self, handle=handle)
        return self._pipe

    def unload(self) -> None:
        clear_model_runtime(self._pipe)
        self._pipe = None
        if self._transparent_decoder is not None:
            try:
                self._transparent_decoder.to("cpu")
            except Exception:
                pass
        self._transparent_decoder = None
        self._layerdiffuse_applied = False
