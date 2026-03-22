from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from PIL import Image

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle
from discoverex.runtime_logging import format_seconds, get_logger

from .fx_param_parsing import as_float, as_int_or_none, as_positive_int, as_str
from .pixart_sigma_background_generation import PixArtSigmaBackgroundGenerationModel

logger = get_logger("discoverex.models.pixart_object")


class PixArtObjectGenerationModel(PixArtSigmaBackgroundGenerationModel):
    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction:
        started = perf_counter()
        output_path_value = as_str(request.params.get("output_path"), fallback="")
        if not output_path_value:
            raise ValueError("FxRequest.params.output_path is required")
        output_path = Path(output_path_value)
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

        image = self._generate_base_image(
            handle=handle,
            prompt=as_str(request.params.get("prompt"), fallback=self.default_prompt),
            negative_prompt=as_str(
                request.params.get("negative_prompt"),
                fallback=self.default_negative_prompt,
            ),
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
        )
        rgba = image.convert("RGBA")
        alpha = Image.new("L", rgba.size, color=255)
        rgba.putalpha(alpha)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(output_path)
        if preview_path is not None:
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            image.convert("RGB").save(preview_path)
        if alpha_path is not None:
            alpha_path.parent.mkdir(parents=True, exist_ok=True)
            alpha.save(alpha_path)
        if visualization_path is not None:
            visualization_path.parent.mkdir(parents=True, exist_ok=True)
            image.convert("RGB").save(visualization_path)

        logger.info(
            "pixart object image saved path=%s duration=%s",
            output_path,
            format_seconds(started),
        )
        return {
            "fx": request.mode or "object_generation",
            "output_path": str(output_path),
            "preview_output_path": str(preview_path) if preview_path is not None else "",
            "alpha_output_path": str(alpha_path) if alpha_path is not None else "",
            "visualization_output_path": (
                str(visualization_path) if visualization_path is not None else ""
            ),
        }
