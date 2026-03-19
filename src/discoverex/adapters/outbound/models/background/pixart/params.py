from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str


@dataclass(frozen=True)
class BackgroundParams:
    output_path: Path
    width: int
    height: int
    seed: int | None
    prompt: str
    negative_prompt: str
    num_inference_steps: int
    guidance_scale: float


@dataclass(frozen=True)
class DetailParams(BackgroundParams):
    image_ref: Path
    strength: float
    enable_extension: bool
    extension_scale_factor: float
    extension_steps: int
    extension_guidance: float
    extension_strength: float


def output_path_from_request(request: Any) -> Path:
    output_path = request.params.get("output_path")
    if not isinstance(output_path, str) or not output_path:
        raise ValueError("FxRequest.params.output_path is required")
    return Path(output_path)


def background_params(request: Any, model: Any) -> BackgroundParams:
    return BackgroundParams(
        output_path=output_path_from_request(request),
        width=as_positive_int(request.params.get("width"), fallback=1024),
        height=as_positive_int(request.params.get("height"), fallback=1024),
        seed=as_int_or_none(request.params.get("seed"), fallback=model.seed),
        prompt=as_str(request.params.get("prompt"), fallback=model.default_prompt),
        negative_prompt=as_str(request.params.get("negative_prompt"), fallback=model.default_negative_prompt),
        num_inference_steps=as_positive_int(request.params.get("num_inference_steps"), fallback=model.default_num_inference_steps),
        guidance_scale=as_float(request.params.get("guidance_scale"), fallback=model.default_guidance_scale),
    )


def canvas_params(request: Any, model: Any) -> tuple[Path, Path, int, int, float]:
    image_ref = request.params.get("image_ref")
    if not isinstance(image_ref, (str, Path)) or not str(image_ref):
        raise ValueError("FxRequest.params.image_ref is required for canvas_upscale")
    return (
        output_path_from_request(request),
        Path(str(image_ref)),
        as_positive_int(request.params.get("width"), fallback=2048),
        as_positive_int(request.params.get("height"), fallback=2048),
        as_float(request.params.get("canvas_scale_factor"), fallback=model.canvas_scale_factor),
    )


def detail_params(request: Any, model: Any) -> DetailParams:
    image_ref = request.params.get("image_ref")
    if not isinstance(image_ref, (str, Path)) or not str(image_ref):
        raise ValueError("FxRequest.params.image_ref is required for detail_reconstruct")
    base = background_params(request, model)
    return DetailParams(
        **base.__dict__,
        image_ref=Path(str(image_ref)),
        strength=as_float(request.params.get("detail_strength"), fallback=as_float(request.params.get("refiner_strength"), fallback=model.detail_strength)),
        enable_extension=bool(request.params.get("enable_highres_extension", model.enable_highres_extension)),
        extension_scale_factor=as_float(request.params.get("extension_scale_factor"), fallback=model.extension_scale_factor),
        extension_steps=as_positive_int(request.params.get("extension_num_inference_steps"), fallback=model.extension_num_inference_steps),
        extension_guidance=as_float(request.params.get("extension_guidance_scale"), fallback=model.extension_guidance_scale),
        extension_strength=as_float(request.params.get("extension_strength"), fallback=model.extension_strength),
    )
