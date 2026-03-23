from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.cache_dirs import resolve_model_cache_dir
from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .pipeline_memory import OffloadMode, configure_diffusers_pipeline
from .realesrgan_background_upscaler import RealEsrganBackgroundUpscalerModel
from .runtime import (
    apply_seed,
    build_runtime_extra,
    normalize_dtype,
    resolve_device,
    resolve_runtime,
    validate_diffusers_runtime,
)
from .runtime_cleanup import clear_model_runtime

logger = get_logger("discoverex.models.realvisxl_lightning_background")

_REQUIRED_SNAPSHOT_FILES = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "tokenizer/vocab.json",
    "tokenizer/merges.txt",
    "tokenizer/special_tokens_map.json",
    "tokenizer/tokenizer_config.json",
    "tokenizer_2/vocab.json",
    "tokenizer_2/merges.txt",
    "tokenizer_2/special_tokens_map.json",
    "tokenizer_2/tokenizer_config.json",
    "unet/config.json",
    "unet/diffusion_pytorch_model.fp16.safetensors",
    "text_encoder/model.fp16.safetensors",
    "text_encoder_2/model.fp16.safetensors",
    "vae/config.json",
    "vae/diffusion_pytorch_model.safetensors",
)


def _configure_scheduler(*, scheduler: Any, sampler_name: str, diffusers: Any) -> Any:
    normalized = sampler_name.strip().lower().replace("+", "p").replace(" ", "_")
    if normalized in {"", "default"}:
        return scheduler
    dpm_cls = getattr(diffusers, "DPMSolverMultistepScheduler")
    if normalized in {
        "dpmpp_sde_karras",
        "dpmpp_sde_2m_karras",
        "dpmpp_2m_sde_karras",
    }:
        return dpm_cls.from_config(
            scheduler.config,
            algorithm_type="sde-dpmsolver++",
            use_karras_sigmas=True,
            solver_order=2,
        )
    if normalized in {"dpmpp_sde", "dpmpp_2m_sde"}:
        return dpm_cls.from_config(
            scheduler.config,
            algorithm_type="sde-dpmsolver++",
            use_karras_sigmas=False,
            solver_order=2,
        )
    raise ValueError(f"unsupported background sampler '{sampler_name}'")


class RealVisXLLightningBackgroundGenerationModel:
    def __init__(
        self,
        model_id: str = "SG161222/RealVisXL_V5.0_Lightning",
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
        sampler: str = "dpmpp_sde_karras",
        hires_sampler: str = "dpmpp_sde_karras",
        default_prompt: str = "cinematic hidden object puzzle background",
        default_negative_prompt: str = "blurry, low quality, artifact",
        default_num_inference_steps: int = 5,
        default_guidance_scale: float = 2.0,
        hires_num_inference_steps: int = 3,
        hires_guidance_scale: float = 2.0,
        hires_strength: float = 0.5,
        canvas_upscaler_model_name: str = "4x-UltraSharp",
        canvas_upscaler_scale: int = 4,
        canvas_upscaler_repo_id: str = "MidnightRunner/Misc",
        canvas_upscaler_filename: str = "4x-UltraSharp.pth",
        canvas_upscaler_weights_cache_dir: str = ".cache/realesrgan",
        model_cache_dir: str = "",
        hf_home: str = "",
        model_cache_policy: str = "local_first",
        allow_remote_model_fetch: bool = True,
        required_local_snapshot: str = "",
        prefetch_model_on_load: bool = False,
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
        self.sampler = sampler
        self.hires_sampler = hires_sampler
        self.default_prompt = default_prompt
        self.default_negative_prompt = default_negative_prompt
        self.default_num_inference_steps = default_num_inference_steps
        self.default_guidance_scale = default_guidance_scale
        self.hires_num_inference_steps = hires_num_inference_steps
        self.hires_guidance_scale = hires_guidance_scale
        self.hires_strength = hires_strength
        self.canvas_upscaler_model_name = canvas_upscaler_model_name
        self.canvas_upscaler_scale = canvas_upscaler_scale
        self.canvas_upscaler_repo_id = canvas_upscaler_repo_id
        self.canvas_upscaler_filename = canvas_upscaler_filename
        self.canvas_upscaler_weights_cache_dir = canvas_upscaler_weights_cache_dir
        self.model_cache_dir = model_cache_dir
        self.hf_home = hf_home
        self.model_cache_policy = model_cache_policy
        self.allow_remote_model_fetch = allow_remote_model_fetch
        self.required_local_snapshot = required_local_snapshot
        self.prefetch_model_on_load = prefetch_model_on_load
        self._base_pipe: Any | None = None
        self._detail_pipe: Any | None = None
        self._canvas_upscaler: RealEsrganBackgroundUpscalerModel | None = None
        self._canvas_upscaler_handle: ModelHandle | None = None

    def load(self, model_ref_or_version: str) -> ModelHandle:
        applied_offload_mode = self._applied_offload_mode()
        logger.info(
            "loading realvisxl lightning background model model_id=%s sampler=%s hires_sampler=%s requested_device=%s requested_dtype=%s requested_offload_mode=%s applied_offload_mode=%s cache_dir=%s hf_home=%s",
            self.model_id,
            self.sampler,
            self.hires_sampler,
            self.device,
            self.dtype,
            self.offload_mode,
            applied_offload_mode,
            self._diffusers_cache_dir(),
            self.hf_home,
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
            runtime="sdxl_text2image",
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
        if request.mode == "canvas_upscale":
            path = self._predict_canvas_upscale(handle=handle, request=request)
            fx_name = "background_canvas_upscale"
        elif request.mode in {"detail_reconstruct", "hires_fix"}:
            path = self._predict_hires_fix(handle=handle, request=request)
            fx_name = (
                "background_detail_reconstruct"
                if request.mode == "detail_reconstruct"
                else "background_hires_fix"
            )
        else:
            path = self._predict_background(handle=handle, request=request)
            fx_name = request.mode or "background_generation"
        logger.info(
            "realvisxl lightning background output saved path=%s fx=%s duration=%s",
            path,
            fx_name,
            format_seconds(started),
        )
        return {"fx": fx_name, "output_path": str(path)}

    def _predict_background(self, *, handle: ModelHandle, request: FxRequest) -> Path:
        output_path = self._output_path(request)
        image = self._generate_image(
            handle=handle,
            prompt=as_str(request.params.get("prompt"), fallback=self.default_prompt),
            negative_prompt=as_str(
                request.params.get("negative_prompt"),
                fallback=self.default_negative_prompt,
            ),
            width=as_positive_int(request.params.get("width"), fallback=1024),
            height=as_positive_int(request.params.get("height"), fallback=1024),
            seed=as_int_or_none(request.params.get("seed"), fallback=self.seed),
            num_inference_steps=as_positive_int(
                request.params.get("num_inference_steps"),
                fallback=self.default_num_inference_steps,
            ),
            guidance_scale=as_float(
                request.params.get("guidance_scale"),
                fallback=self.default_guidance_scale,
            ),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        return output_path

    def _predict_canvas_upscale(self, *, handle: ModelHandle, request: FxRequest) -> Path:
        output_path = self._output_path(request)
        image_ref = request.image_ref
        if not isinstance(image_ref, (str, Path)) or not str(image_ref):
            raise ValueError("FxRequest.image_ref is required")
        width = as_positive_int(request.params.get("width"), fallback=2048)
        height = as_positive_int(request.params.get("height"), fallback=2048)
        upscaler = self._load_canvas_upscaler(handle)
        prediction = upscaler.predict(
            self._canvas_upscaler_handle or handle,
            FxRequest(
                mode="canvas_upscale",
                image_ref=str(image_ref),
                params={
                    "output_path": str(output_path),
                    "width": width,
                    "height": height,
                },
            ),
        )
        return Path(str(prediction.get("output_path") or output_path))

    def _predict_hires_fix(self, *, handle: ModelHandle, request: FxRequest) -> Path:
        from PIL import Image  # type: ignore

        output_path = self._output_path(request)
        image_ref = request.image_ref
        if not isinstance(image_ref, (str, Path)) or not str(image_ref):
            raise ValueError("FxRequest.image_ref is required")
        source_path = Path(str(image_ref))
        width = as_positive_int(request.params.get("width"), fallback=1024)
        height = as_positive_int(request.params.get("height"), fallback=1024)
        prompt = as_str(request.params.get("prompt"), fallback=self.default_prompt)
        negative_prompt = as_str(
            request.params.get("negative_prompt"),
            fallback=self.default_negative_prompt,
        )
        seed = as_int_or_none(request.params.get("seed"), fallback=self.seed)
        num_inference_steps = as_positive_int(
            request.params.get("num_inference_steps"),
            fallback=self.hires_num_inference_steps,
        )
        guidance_scale = as_float(
            request.params.get("guidance_scale"),
            fallback=self.hires_guidance_scale,
        )
        strength = as_float(
            request.params.get("detail_strength"),
            fallback=as_float(
                request.params.get("refiner_strength"),
                fallback=self.hires_strength,
            ),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path).convert("RGB") as source_image:
            resized = source_image.resize((width, height), Image.Resampling.LANCZOS)
            reconstructed = self._reconstruct_image(
                handle=handle,
                image=resized,
                prompt=prompt,
                negative_prompt=negative_prompt,
                seed=seed,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                strength=strength,
            )
            reconstructed.save(output_path)
        return output_path

    def _load_base_pipe(self, handle: ModelHandle) -> Any:
        if self._base_pipe is not None:
            return self._base_pipe
        cache_dir = self._diffusers_cache_dir()
        variant = self._variant_for_handle(handle)
        applied_offload_mode = self._applied_offload_mode()
        started = perf_counter()
        logger.info(
            "realvisxl background base pipeline materialization started model_id=%s revision=%s dtype=%s variant=%s requested_offload_mode=%s applied_offload_mode=%s cache_dir=%s",
            self.model_id,
            self.revision,
            handle.dtype,
            variant or "default",
            self.offload_mode,
            applied_offload_mode,
            cache_dir,
        )
        self._log_cache_probe(cache_dir=cache_dir, pipeline_kind="base")
        try:
            import torch  # type: ignore
            import diffusers  # type: ignore
        except Exception as exc:
            runtime = resolve_runtime()
            validate_diffusers_runtime(runtime)
            logger.exception(
                "realvisxl background base pipeline import failed model_id=%s cache_dir=%s",
                self.model_id,
                cache_dir,
            )
            raise RuntimeError(
                "diffusers text-to-image pipeline import failed. Install compatible ml-gpu or ml-cpu dependencies."
            ) from exc
        torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        try:
            load_started = perf_counter()
            pipe = self._from_pretrained_with_cache_policy(
                pipeline_kind="base",
                loader=diffusers.AutoPipelineForText2Image.from_pretrained,  # type: ignore[no-untyped-call]
                cache_dir=cache_dir,
                torch_dtype=torch_dtype,
                variant=variant,
            )
            logger.info(
                "realvisxl background base pipeline from_pretrained completed model_id=%s duration=%s",
                self.model_id,
                format_seconds(load_started),
            )
            scheduler_started = perf_counter()
            pipe.scheduler = _configure_scheduler(
                scheduler=pipe.scheduler,
                sampler_name=self.sampler,
                diffusers=diffusers,
            )
            logger.info(
                "realvisxl background base pipeline scheduler configured sampler=%s duration=%s",
                self.sampler,
                format_seconds(scheduler_started),
            )
            configure_started = perf_counter()
            self._base_pipe = configure_diffusers_pipeline(
                pipe,
                handle=handle,
                offload_mode=applied_offload_mode,
                enable_attention_slicing=self.enable_attention_slicing,
                enable_vae_slicing=self.enable_vae_slicing,
                enable_vae_tiling=self.enable_vae_tiling,
                enable_xformers_memory_efficient_attention=self.enable_xformers_memory_efficient_attention,
                enable_fp8_layerwise_casting=self.enable_fp8_layerwise_casting,
                enable_channels_last=self.enable_channels_last,
            )
            logger.info(
                "realvisxl background base pipeline runtime configured applied_offload_mode=%s duration=%s",
                applied_offload_mode,
                format_seconds(configure_started),
            )
        except Exception:
            logger.exception(
                "realvisxl background base pipeline materialization failed model_id=%s revision=%s dtype=%s variant=%s requested_offload_mode=%s applied_offload_mode=%s cache_dir=%s",
                self.model_id,
                self.revision,
                handle.dtype,
                variant or "default",
                self.offload_mode,
                applied_offload_mode,
                cache_dir,
            )
            raise
        logger.info(
            "realvisxl background base pipeline ready model_id=%s duration=%s",
            self.model_id,
            format_seconds(started),
        )
        return self._base_pipe

    def _load_detail_pipe(self, handle: ModelHandle) -> Any:
        if self._detail_pipe is not None:
            return self._detail_pipe
        cache_dir = self._diffusers_cache_dir()
        variant = self._variant_for_handle(handle)
        applied_offload_mode = self._applied_offload_mode()
        started = perf_counter()
        logger.info(
            "realvisxl background detail pipeline materialization started model_id=%s revision=%s dtype=%s variant=%s requested_offload_mode=%s applied_offload_mode=%s cache_dir=%s",
            self.model_id,
            self.revision,
            handle.dtype,
            variant or "default",
            self.offload_mode,
            applied_offload_mode,
            cache_dir,
        )
        self._log_cache_probe(cache_dir=cache_dir, pipeline_kind="detail")
        try:
            import torch  # type: ignore
            import diffusers  # type: ignore
        except Exception as exc:
            runtime = resolve_runtime()
            validate_diffusers_runtime(runtime)
            logger.exception(
                "realvisxl background detail pipeline import failed model_id=%s cache_dir=%s",
                self.model_id,
                cache_dir,
            )
            raise RuntimeError(
                "diffusers image-to-image pipeline import failed. Install compatible ml-gpu or ml-cpu dependencies."
            ) from exc
        torch_dtype = torch.float32 if "32" in handle.dtype else torch.float16
        try:
            load_started = perf_counter()
            pipe = self._from_pretrained_with_cache_policy(
                pipeline_kind="detail",
                loader=diffusers.AutoPipelineForImage2Image.from_pretrained,  # type: ignore[no-untyped-call]
                cache_dir=cache_dir,
                torch_dtype=torch_dtype,
                variant=variant,
            )
            logger.info(
                "realvisxl background detail pipeline from_pretrained completed model_id=%s duration=%s",
                self.model_id,
                format_seconds(load_started),
            )
            scheduler_started = perf_counter()
            pipe.scheduler = _configure_scheduler(
                scheduler=pipe.scheduler,
                sampler_name=self.hires_sampler,
                diffusers=diffusers,
            )
            logger.info(
                "realvisxl background detail pipeline scheduler configured sampler=%s duration=%s",
                self.hires_sampler,
                format_seconds(scheduler_started),
            )
            configure_started = perf_counter()
            self._detail_pipe = configure_diffusers_pipeline(
                pipe,
                handle=handle,
                offload_mode=applied_offload_mode,
                enable_attention_slicing=self.enable_attention_slicing,
                enable_vae_slicing=self.enable_vae_slicing,
                enable_vae_tiling=self.enable_vae_tiling,
                enable_xformers_memory_efficient_attention=self.enable_xformers_memory_efficient_attention,
                enable_fp8_layerwise_casting=self.enable_fp8_layerwise_casting,
                enable_channels_last=self.enable_channels_last,
            )
            logger.info(
                "realvisxl background detail pipeline runtime configured applied_offload_mode=%s duration=%s",
                applied_offload_mode,
                format_seconds(configure_started),
            )
        except Exception:
            logger.exception(
                "realvisxl background detail pipeline materialization failed model_id=%s revision=%s dtype=%s variant=%s requested_offload_mode=%s applied_offload_mode=%s cache_dir=%s",
                self.model_id,
                self.revision,
                handle.dtype,
                variant or "default",
                self.offload_mode,
                applied_offload_mode,
                cache_dir,
            )
            raise
        logger.info(
            "realvisxl background detail pipeline ready model_id=%s duration=%s",
            self.model_id,
            format_seconds(started),
        )
        return self._detail_pipe

    def _generate_image(
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
        inference_started = perf_counter()
        logger.info(
            "realvisxl background inference started pipeline=base width=%s height=%s steps=%s guidance_scale=%s seed=%s",
            width,
            height,
            num_inference_steps,
            guidance_scale,
            seed,
        )
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
            raise RuntimeError("text2image pipeline returned no images")
        logger.info(
            "realvisxl background inference completed pipeline=base duration=%s",
            format_seconds(inference_started),
        )
        return images[0]

    def _reconstruct_image(
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
        try:
            import torch  # type: ignore
        except Exception as exc:
            raise RuntimeError("torch runtime unavailable") from exc
        if strength <= 0.0:
            return image
        generator = None
        if seed is not None:
            generator = torch.Generator(device="cpu").manual_seed(seed)
        pipe = self._load_detail_pipe(handle)
        inference_started = perf_counter()
        logger.info(
            "realvisxl background inference started pipeline=detail steps=%s guidance_scale=%s strength=%s seed=%s",
            num_inference_steps,
            guidance_scale,
            strength,
            seed,
        )
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image,
            strength=strength,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
        )
        images = getattr(result, "images", None)
        if not images:
            return image
        logger.info(
            "realvisxl background inference completed pipeline=detail duration=%s",
            format_seconds(inference_started),
        )
        return images[0]

    def _load_canvas_upscaler(
        self, handle: ModelHandle
    ) -> RealEsrganBackgroundUpscalerModel:
        if self._canvas_upscaler is None:
            self._canvas_upscaler = RealEsrganBackgroundUpscalerModel(
                model_name=self.canvas_upscaler_model_name,
                scale=self.canvas_upscaler_scale,
                weights_repo_id=self.canvas_upscaler_repo_id,
                weights_filename=self.canvas_upscaler_filename,
                device=self.device,
                dtype=self.dtype,
                strict_runtime=self.strict_runtime,
                weights_cache_dir=self.canvas_upscaler_weights_cache_dir,
                model_cache_dir=self.model_cache_dir,
                hf_home=self.hf_home,
            )
            self._canvas_upscaler_handle = self._canvas_upscaler.load(
                f"{handle.version}:canvas_upscale"
            )
        return self._canvas_upscaler

    def _applied_offload_mode(self) -> OffloadMode:
        return "model" if self.offload_mode == "sequential" else self.offload_mode

    def _variant_for_handle(self, handle: ModelHandle) -> str | None:
        return "fp16" if "16" in str(handle.dtype) else None

    def _diffusers_cache_dir(self) -> str:
        if self.hf_home.strip():
            return str(Path(self.hf_home).expanduser())
        return str(
            resolve_model_cache_dir(model_cache_dir=self.model_cache_dir) / "hf"
        )

    def _log_cache_probe(self, *, cache_dir: str, pipeline_kind: str) -> None:
        try:
            cache_path = Path(cache_dir)
            exists = cache_path.exists()
            entries = sum(1 for _ in cache_path.iterdir()) if exists else 0
            snapshot = self._snapshot_dir(cache_dir)
            missing = self._missing_snapshot_files(cache_dir)
            logger.info(
                "realvisxl background cache probe pipeline=%s cache_dir=%s exists=%s entries=%s snapshot=%s missing_required=%s",
                pipeline_kind,
                cache_dir,
                exists,
                entries,
                snapshot,
                ",".join(missing) if missing else "none",
            )
        except Exception:
            logger.debug(
                "realvisxl background cache probe failed pipeline=%s cache_dir=%s",
                pipeline_kind,
                cache_dir,
                exc_info=True,
            )

    def _from_pretrained_with_cache_policy(
        self,
        *,
        pipeline_kind: str,
        loader: Any,
        cache_dir: str,
        torch_dtype: Any,
        variant: str | None,
    ) -> Any:
        local_only = self._should_try_local_first(cache_dir)
        kwargs = {
            "revision": self.revision,
            "torch_dtype": torch_dtype,
            "variant": variant,
            "use_safetensors": True,
            "add_watermarker": False,
            "cache_dir": cache_dir,
        }
        if local_only:
            logger.info(
                "realvisxl background %s pipeline local-only attempt started model_id=%s variant=%s cache_dir=%s snapshot=%s",
                pipeline_kind,
                self.model_id,
                variant or "default",
                cache_dir,
                self._snapshot_dir(cache_dir),
            )
            try:
                return loader(
                    self.model_id,
                    local_files_only=True,
                    **kwargs,
                )
            except Exception as exc:
                logger.warning(
                    "realvisxl background %s pipeline local-only attempt failed model_id=%s cache_dir=%s reason=%s",
                    pipeline_kind,
                    self.model_id,
                    cache_dir,
                    exc,
                )
                if not self.allow_remote_model_fetch:
                    raise
        logger.info(
            "realvisxl background %s pipeline remote fallback started model_id=%s variant=%s cache_dir=%s local_policy=%s allow_remote=%s",
            pipeline_kind,
            self.model_id,
            variant or "default",
            cache_dir,
            self.model_cache_policy,
            self.allow_remote_model_fetch,
        )
        return loader(self.model_id, **kwargs)

    def _should_try_local_first(self, cache_dir: str) -> bool:
        policy = self.model_cache_policy.strip().lower()
        if policy not in {"local_first", "remote_first"}:
            policy = "local_first"
        if policy != "local_first":
            return False
        if self.required_local_snapshot.strip() and self._snapshot_dir(cache_dir) is None:
            return False
        return not self._missing_snapshot_files(cache_dir)

    def _snapshot_dir(self, cache_dir: str) -> str | None:
        repo_root = Path(cache_dir) / "hub" / self._repo_cache_key()
        snapshot_ref = self.required_local_snapshot.strip()
        if not snapshot_ref:
            ref_path = repo_root / "refs" / self.revision
            if ref_path.exists():
                snapshot_ref = ref_path.read_text(encoding="utf-8").strip()
        if not snapshot_ref:
            return None
        snapshot_path = repo_root / "snapshots" / snapshot_ref
        if not snapshot_path.exists():
            return None
        return str(snapshot_path)

    def _missing_snapshot_files(self, cache_dir: str) -> list[str]:
        snapshot_dir = self._snapshot_dir(cache_dir)
        if snapshot_dir is None:
            return list(_REQUIRED_SNAPSHOT_FILES)
        root = Path(snapshot_dir)
        return [
            relative
            for relative in _REQUIRED_SNAPSHOT_FILES
            if not (root / relative).exists()
        ]

    def _repo_cache_key(self) -> str:
        return f"models--{self.model_id.replace('/', '--')}"

    def _output_path(self, request: FxRequest) -> Path:
        output_path = request.params.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")
        return Path(output_path)

    def unload(self) -> None:
        if self._canvas_upscaler is not None:
            self._canvas_upscaler.unload()
        clear_model_runtime(self._base_pipe, self._detail_pipe)
        self._base_pipe = None
        self._detail_pipe = None
        self._canvas_upscaler = None
        self._canvas_upscaler_handle = None
