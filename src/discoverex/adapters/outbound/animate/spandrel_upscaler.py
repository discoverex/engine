"""AI super-resolution upscaler using Spandrel (Real-ESRGAN etc).

Generates actual detail — not just interpolation like PIL Lanczos.
Model is loaded on first call and cached. GPU memory is released after use.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import torch
from PIL import Image

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "ComfyUI/models/upscale_models/RealESRGAN_x4plus.pth"


class SpandrelUpscaler:
    """ImageUpscalerPort implementation using Spandrel (Real-ESRGAN 4x).

    - AI 기반 초해상도: 디테일을 실제로 생성
    - 타일 처리: 큰 이미지도 OOM 없이 처리
    - 사용 후 GPU 메모리 즉시 반환
    """

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL,
        tile_size: int = 512,
        tile_overlap: int = 32,
        device: str = "cuda",
    ) -> None:
        self._model_path = Path(model_path)
        if not self._model_path.is_absolute():
            self._model_path = Path.home() / model_path
        self._tile_size = tile_size
        self._tile_overlap = tile_overlap
        self._device = device
        self._model = None

    def upscale(
        self, image: Path, scale_factor: float, art_style: str = "illustration",
    ) -> Path:
        if art_style == "pixel_art":
            return self._nearest_upscale(image, scale_factor)

        return self._ai_upscale(image, scale_factor)

    def _ai_upscale(self, image: Path, scale_factor: float) -> Path:
        import spandrel

        raw = Image.open(image)
        # RGBA 투명 영역을 흰색으로 채운 후 RGB 변환 (검은 박스 방지)
        if raw.mode == "RGBA":
            bg = Image.new("RGB", raw.size, (255, 255, 255))
            bg.paste(raw, mask=raw.split()[3])
            src = bg
        else:
            src = raw.convert("RGB")
        ow, oh = src.size

        # 모델 로드 (최초 1회)
        if self._model is None:
            self._model = spandrel.ModelLoader().load_from_file(
                str(self._model_path),
            )
            self._model = self._model.eval()
        model_scale = self._model.scale  # Real-ESRGAN = 4x 고정

        try:
            self._model = self._model.to(self._device)
            arr = np.array(src).astype(np.float32) / 255.0
            tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)
            tensor = tensor.to(self._device)

            with torch.no_grad():
                out = self._tiled_inference(tensor)

            out_arr = out.squeeze(0).permute(1, 2, 0).cpu().numpy()
            out_arr = np.clip(out_arr * 255, 0, 255).astype(np.uint8)
            result = Image.fromarray(out_arr)

            # 모델 스케일(4x)과 요청 배율이 다르면 리사이즈
            if abs(scale_factor - model_scale) > 0.1:
                target_w = int(ow * scale_factor)
                target_h = int(oh * scale_factor)
                result = result.resize(
                    (target_w, target_h), Image.Resampling.LANCZOS,
                )
        finally:
            self._model = self._model.to("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        out_path = image.parent / f"{image.stem}_upscaled{image.suffix}"
        result.save(out_path)

        logger.info(
            "[SpandrelUpscaler] %dx%d -> %dx%d (AI x%d, art=%s)",
            ow, oh, result.size[0], result.size[1], model_scale, "ai",
        )
        return out_path

    def _tiled_inference(self, tensor: torch.Tensor) -> torch.Tensor:
        """타일 단위 추론 — 큰 이미지도 OOM 없이 처리."""
        _, _, h, w = tensor.shape
        if h <= self._tile_size and w <= self._tile_size:
            return self._model(tensor)

        scale = self._model.scale
        out = torch.zeros(
            1, 3, h * scale, w * scale,
            device=tensor.device, dtype=tensor.dtype,
        )
        t, ov = self._tile_size, self._tile_overlap

        for y in range(0, h, t - ov):
            for x in range(0, w, t - ov):
                y2 = min(y + t, h)
                x2 = min(x + t, w)
                tile = tensor[:, :, y:y2, x:x2]
                tile_out = self._model(tile)
                oy, ox = y * scale, x * scale
                oy2, ox2 = y2 * scale, x2 * scale
                out[:, :, oy:oy2, ox:ox2] = tile_out

        return out

    @staticmethod
    def _nearest_upscale(image: Path, scale_factor: float) -> Path:
        src = Image.open(image)
        new_w = int(src.size[0] * scale_factor)
        new_h = int(src.size[1] * scale_factor)
        result = src.resize((new_w, new_h), Image.Resampling.NEAREST)
        out_path = image.parent / f"{image.stem}_upscaled{image.suffix}"
        result.save(out_path)
        logger.info(
            "[SpandrelUpscaler] %dx%d -> %dx%d (nearest, pixel_art)",
            src.size[0], src.size[1], new_w, new_h,
        )
        return out_path
