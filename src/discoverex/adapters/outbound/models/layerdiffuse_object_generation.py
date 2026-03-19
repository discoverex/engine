from __future__ import annotations

import importlib
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from PIL import Image  # type: ignore

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .model_loading import load_state_dict_materialized
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

logger = get_logger("discoverex.models.layerdiffuse_object")

_ATTN_OFFSET_URL = (
    "https://huggingface.co/lllyasviel/LayerDiffuse_Diffusers/resolve/main/"
    "ld_diffusers_sdxl_attn.safetensors"
)
_TRANSPARENT_DECODER_URL = (
    "https://huggingface.co/lllyasviel/LayerDiffuse_Diffusers/resolve/main/"
    "ld_diffusers_sdxl_vae_transparent_decoder.safetensors"
)


class LayerDiffuseObjectGenerationModel:
    def __init__(
        self,
        model_id: str = "SG161222/RealVisXL_V4.0",
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
        default_prompt: str = "isolated single object on a transparent background",
        default_negative_prompt: str = "busy scene, environment, multiple objects, floor, wall, clutter, blurry, low quality, artifact",
        default_num_inference_steps: int = 30,
        default_guidance_scale: float = 5.0,
        weights_cache_dir: str = ".cache/layerdiffuse",
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
        self.default_num_inference_steps = default_num_inference_steps
        self.default_guidance_scale = default_guidance_scale
        self.weights_cache_dir = str(_resolve_shared_cache_dir(weights_cache_dir))
        self._pipe: Any | None = None
        self._transparent_decoder: Any | None = None
        self._layerdiffuse_applied = False

    def load(self, model_ref_or_version: str) -> ModelHandle:
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
        output_path = request.params.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")
        width = as_positive_int(request.params.get("width"), fallback=512)
        height = as_positive_int(request.params.get("height"), fallback=512)
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
        image = self._generate_rgba(
            handle=handle,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            seed=seed,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        logger.info(
            "layerdiffuse object image saved path=%s duration=%s",
            path,
            format_seconds(started),
        )
        return {"fx": request.mode or "object_generation", "output_path": str(path)}

    def _generate_rgba(
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
        import torch  # type: ignore

        pipe = self._load_pipeline(handle)
        execution_device = getattr(pipe, "_execution_device", handle.device)
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            width=width,
            height=height,
            generator=generator,
            output_type="latent",
        )
        latents = result.images
        decoder = self._load_transparent_decoder(handle)
        vae = pipe.vae
        vae = vae.to(device=execution_device, dtype=vae.dtype)
        decoder = decoder.to(device=execution_device, dtype=vae.dtype)
        latents = (
            latents.to(device=execution_device, dtype=vae.dtype)
            / vae.config.scaling_factor
        )
        rgba_images, _ = decoder(vae, latents)
        return Image.fromarray(rgba_images[0], mode="RGBA")

    def _load_pipeline(self, handle: ModelHandle) -> Any:
        if self._pipe is not None:
            return self._pipe
        try:
            import safetensors.torch as sf  # type: ignore
            import torch  # type: ignore
            from diffusers import (  # type: ignore
                AutoPipelineForText2Image,
                DPMSolverMultistepScheduler,
            )
        except Exception as exc:
            raise RuntimeError("layerdiffuse runtime unavailable") from exc

        variant = "fp16" if "16" in handle.dtype else None
        torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        pipe = AutoPipelineForText2Image.from_pretrained(
            self.model_id,
            revision=self.revision,
            torch_dtype=torch_dtype,
            variant=variant,
        )
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config,
            use_karras_sigmas=True,
            algorithm_type="dpmsolver++",
            solver_order=2,
        )
        attn_path = self._download_weight(
            url=_ATTN_OFFSET_URL,
            filename="ld_diffusers_sdxl_attn.safetensors",
        )
        if not self._layerdiffuse_applied:
            offset = sf.load_file(str(attn_path))
            base_state = pipe.unet.state_dict()
            merged_state = {
                key: base_state[key] + offset[key] if key in offset else base_state[key]
                for key in base_state
            }
            load_state_dict_materialized(pipe.unet, merged_state, strict=True)
            self._layerdiffuse_applied = True
        self._pipe = configure_diffusers_pipeline(
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
        return self._pipe

    def _load_transparent_decoder(self, handle: ModelHandle) -> Any:
        if self._transparent_decoder is not None:
            return self._transparent_decoder
        import torch  # type: ignore

        transparent_vae = importlib.import_module(
            "discoverex.adapters.outbound.models.layerdiffuse_transparent_vae"
        )
        decoder_path = self._download_weight(
            url=_TRANSPARENT_DECODER_URL,
            filename="ld_diffusers_sdxl_vae_transparent_decoder.safetensors",
        )
        decoder_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        self._transparent_decoder = transparent_vae.TransparentVAEDecoder(
            str(decoder_path),
            dtype=decoder_dtype,
        )
        return self._transparent_decoder

    def _download_weight(self, *, url: str, filename: str) -> Path:
        from torch.hub import download_url_to_file  # type: ignore

        cache_dir = Path(self.weights_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / filename
        if target.exists():
            return target
        temp = target.with_suffix(target.suffix + ".tmp")
        download_url_to_file(url, str(temp))
        temp.replace(target)
        return target

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


def _resolve_shared_cache_dir(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    model_cache_dir = os.getenv("MODEL_CACHE_DIR", "").strip()
    if model_cache_dir:
        base = Path(model_cache_dir).expanduser()
        parts = [part for part in path.parts if part not in {".", ".cache"}]
        return base.joinpath(*parts) if parts else base
    hf_home = os.getenv("HF_HOME", "").strip()
    if hf_home:
        base = Path(hf_home).expanduser()
    else:
        base = Path.home() / ".cache" / "huggingface" / "discoverex"
    parts = [part for part in path.parts if part not in {"."}]
    if parts and parts[0] == ".cache":
        parts = parts[1:]
    return base.joinpath(*parts) if parts else base
