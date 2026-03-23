from __future__ import annotations

import os
import hashlib
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from discoverex.cache_dirs import resolve_model_cache_dir
from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .runtime import apply_seed, normalize_dtype, resolve_device, resolve_runtime
from .runtime_cleanup import clear_model_runtime

logger = get_logger("discoverex.models.realesrgan_upscaler")


class RealEsrganBackgroundUpscalerModel:
    def __init__(
        self,
        model_name: str = "RealESRGAN_x2plus",
        scale: int = 2,
        weights_repo_id: str = "",
        weights_filename: str = "",
        device: str = "cuda",
        dtype: str = "float16",
        tile: int = 512,
        tile_pad: int = 16,
        pre_pad: int = 0,
        strict_runtime: bool = False,
        weights_cache_dir: str = ".cache/realesrgan",
        model_cache_dir: str = "",
        hf_home: str = "",
    ) -> None:
        self.model_name = model_name
        self.scale = max(1, int(scale))
        self.weights_repo_id = weights_repo_id.strip()
        self.weights_filename = weights_filename.strip()
        self.device = device
        self.dtype = dtype
        self.tile = tile
        self.tile_pad = tile_pad
        self.pre_pad = pre_pad
        self.strict_runtime = strict_runtime
        self.weights_cache_dir = str(
            _resolve_shared_cache_dir(
                weights_cache_dir,
                model_cache_dir=model_cache_dir,
                hf_home=hf_home,
            )
        )
        self._upsampler: Any | None = None

    def load(self, model_ref_or_version: str) -> ModelHandle:
        runtime = resolve_runtime()
        selected_device = resolve_device(self.device, runtime.torch)
        selected_dtype = str(normalize_dtype(self.dtype, runtime.torch))
        if self.strict_runtime and selected_device != self.device:
            raise RuntimeError(f"requested device '{self.device}' is unavailable")
        apply_seed(None, runtime.torch)
        return ModelHandle(
            name="background_upscaler_model",
            version=model_ref_or_version,
            runtime="realesrgan",
            model_id=self.model_name,
            device=selected_device,
            dtype=selected_dtype,
        )

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction:
        import numpy as np
        from PIL import Image  # type: ignore

        image_ref = request.image_ref
        if not isinstance(image_ref, (str, Path)) or not str(image_ref):
            raise ValueError("FxRequest.image_ref is required")
        output_path = request.params.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")
        source_path = Path(str(image_ref))
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        width = int(request.params.get("width") or 0)
        height = int(request.params.get("height") or 0)
        with Image.open(source_path).convert("RGB") as image:
            target_w = width if width > 0 else image.width
            target_h = height if height > 0 else image.height
            upsampler = self._load_upsampler(handle)
            source = np.asarray(image)[:, :, ::-1]
            outscale = max(
                target_w / max(1, image.width), target_h / max(1, image.height), 1.0
            )
            output, _ = upsampler.enhance(source, outscale=outscale)
            upscaled = Image.fromarray(output[:, :, ::-1], mode="RGB")
            if upscaled.width != target_w or upscaled.height != target_h:
                upscaled = upscaled.resize(
                    (target_w, target_h), Image.Resampling.LANCZOS
                )
            upscaled.save(target_path)
        return {
            "fx": request.mode or "background_upscale",
            "output_path": str(target_path),
        }

    def _load_upsampler(self, handle: ModelHandle) -> Any:
        if self._upsampler is not None:
            return self._upsampler
        _ensure_torchvision_compat()
        started = perf_counter()
        try:
            import torch  # type: ignore
            from basicsr.archs.rrdbnet_arch import RRDBNet  # type: ignore
            from realesrgan import RealESRGANer  # type: ignore
        except Exception as exc:
            logger.exception(
                "realesrgan background upscaler import failed model=%s cache_dir=%s",
                self.model_name,
                self.weights_cache_dir,
            )
            raise RuntimeError(
                "RealESRGAN runtime unavailable. Install ml-gpu dependencies with realesrgan/basicsr."
            ) from exc
        model_urls = {
            "RealESRGAN_x4plus": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
            "RealESRGAN_x2plus": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        }
        model_scales = {
            "RealESRGAN_x4plus": 4,
            "RealESRGAN_x2plus": 2,
        }
        weights_dir = Path(self.weights_cache_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        model_scale = model_scales.get(self.model_name, self.scale)
        logger.info(
            "loading realesrgan background upscaler model=%s device=%s tile=%s weights_cache_dir=%s source=%s",
            self.model_name,
            handle.device,
            self.tile,
            self.weights_cache_dir,
            "hf_hub" if self.weights_repo_id and self.weights_filename else "url",
        )
        if self.weights_repo_id and self.weights_filename:
            from huggingface_hub import hf_hub_download  # type: ignore

            logger.info(
                "realesrgan weight fetch started repo_id=%s filename=%s",
                self.weights_repo_id,
                self.weights_filename,
            )
            model_path = hf_hub_download(
                repo_id=self.weights_repo_id,
                filename=self.weights_filename,
                cache_dir=str(weights_dir),
            )
            logger.info(
                "realesrgan weight fetch completed repo_id=%s filename=%s path=%s",
                self.weights_repo_id,
                self.weights_filename,
                model_path,
            )
            model_path = self._normalize_checkpoint_if_needed(
                model_path=Path(model_path),
                torch_module=torch,
            )
        elif self.model_name in model_urls:
            from basicsr.utils.download_util import load_file_from_url  # type: ignore

            target_file = weights_dir / f"{self.model_name}.pth"
            cache_hit = target_file.exists()
            logger.info(
                "realesrgan weight fetch started url=%s target=%s cache_hit=%s",
                model_urls[self.model_name],
                target_file,
                cache_hit,
            )
            model_path = load_file_from_url(
                url=model_urls[self.model_name],
                model_dir=str(weights_dir),
                progress=True,
                file_name=f"{self.model_name}.pth",
            )
            logger.info(
                "realesrgan weight fetch completed target=%s path=%s",
                target_file,
                model_path,
            )
        else:
            raise ValueError(f"unsupported RealESRGAN model: {self.model_name}")
        rrdb = RRDBNet(
            num_in_ch=3,
            num_out_ch=3,
            num_feat=64,
            num_block=23,
            num_grow_ch=32,
            scale=model_scale,
        )
        use_half = bool(
            "16" in handle.dtype
            and handle.device == "cuda"
            and torch.cuda.is_available()
        )
        gpu_id = 0 if handle.device == "cuda" and torch.cuda.is_available() else None
        self._upsampler = RealESRGANer(
            scale=model_scale,
            model_path=model_path,
            model=rrdb,
            tile=max(0, int(self.tile)),
            tile_pad=max(0, int(self.tile_pad)),
            pre_pad=max(0, int(self.pre_pad)),
            half=use_half,
            gpu_id=gpu_id,
        )
        logger.info(
            "realesrgan background upscaler ready model=%s duration=%s",
            self.model_name,
            format_seconds(started),
        )
        return self._upsampler

    def unload(self) -> None:
        clear_model_runtime(self._upsampler)
        self._upsampler = None

    def _normalize_checkpoint_if_needed(
        self, *, model_path: Path, torch_module: Any
    ) -> Path:
        try:
            checkpoint = torch_module.load(str(model_path), map_location="cpu")
        except Exception:
            logger.warning(
                "realesrgan checkpoint probe failed model=%s path=%s",
                self.model_name,
                model_path,
                exc_info=True,
            )
            return model_path
        state_dict = _extract_state_dict(checkpoint)
        if state_dict is None:
            return model_path
        if isinstance(checkpoint, dict) and (
            "params" in checkpoint or "params_ema" in checkpoint
        ):
            return model_path
        normalized_path = model_path.with_name(
            f"{model_path.stem}.{_stable_checkpoint_id(model_path=model_path)}.normalized.pth"
        )
        if not normalized_path.exists():
            torch_module.save({"params_ema": state_dict}, str(normalized_path))
            logger.info(
                "realesrgan checkpoint normalized model=%s source=%s normalized=%s",
                self.model_name,
                model_path,
                normalized_path,
            )
        return normalized_path


def _resolve_shared_cache_dir(
    raw_path: str,
    *,
    model_cache_dir: str = "",
    hf_home: str = "",
) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    base = resolve_model_cache_dir(model_cache_dir=model_cache_dir)
    parts = [part for part in path.parts if part not in {".", ".cache"}]
    if parts:
        return base.joinpath(*parts)
    if hf_home.strip():
        base = Path(hf_home).expanduser()
    else:
        base = Path.home() / ".cache" / "huggingface" / "discoverex"
    parts = [part for part in path.parts if part not in {"."}]
    if parts and parts[0] == ".cache":
        parts = parts[1:]
    return base.joinpath(*parts) if parts else base


def _ensure_torchvision_compat() -> None:
    if "torchvision.transforms.functional_tensor" in sys.modules:
        return
    try:
        from torchvision.transforms import _functional_tensor  # type: ignore
    except Exception:
        return
    sys.modules["torchvision.transforms.functional_tensor"] = _functional_tensor


def _extract_state_dict(checkpoint: Any) -> dict[str, Any] | None:
    if not isinstance(checkpoint, dict):
        return None
    for key in ("params_ema", "params", "state_dict", "model_state_dict", "model"):
        value = checkpoint.get(key)
        if isinstance(value, dict) and value:
            return value
    if checkpoint and all(isinstance(key, str) for key in checkpoint):
        return checkpoint
    return None


def _stable_checkpoint_id(*, model_path: Path) -> str:
    stat = model_path.stat()
    raw = f"{model_path.resolve()}:{stat.st_size}:{int(stat.st_mtime)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
