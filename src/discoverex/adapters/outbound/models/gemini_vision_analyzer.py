"""VisionAnalysisPort implementation — Gemini Vision motion parameter analysis."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from discoverex.domain.animate import VisionAnalysis

from .gemini_common import GeminiClientMixin, parse_gemini_json
from .gemini_vision_prompt import VISION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeminiVisionAnalyzer(GeminiClientMixin):
    """Analyze image via Gemini Vision to determine all WAN I2V parameters."""

    def __init__(self, model: str = "gemini-2.5-flash", max_retries: int = 3) -> None:
        super().__init__(model=model, max_retries=max_retries, temperature=0.3, max_output_tokens=5000)

    def analyze(self, image: Path) -> VisionAnalysis:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._call_gemini(image, VISION_SYSTEM_PROMPT)
            except Exception as e:
                last_error = e
                logger.warning(f"[Vision] attempt {attempt}/{self._max_retries} failed: {e}")
                if attempt < self._max_retries:
                    time.sleep(2)
        raise RuntimeError(f"[Vision] all {self._max_retries} attempts failed: {last_error}")

    def analyze_with_exclusion(self, image: Path, exclude_action: str) -> VisionAnalysis:
        exclusion_note = (
            f"\n\nIMPORTANT: The following action FAILED. Do NOT choose it again:\n"
            f'  EXCLUDED: "{exclude_action}"\nChoose a DIFFERENT motion.'
        )
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._call_gemini(image, VISION_SYSTEM_PROMPT + exclusion_note, temperature=0.5)
            except Exception as e:
                last_error = e
                logger.warning(f"[Vision] exclusion attempt {attempt} failed: {e}")
                if attempt < self._max_retries:
                    time.sleep(2)
        raise RuntimeError(f"[Vision] exclusion analysis failed: {last_error}")

    def _call_gemini(self, image: Path, prompt: str, temperature: float | None = None) -> VisionAnalysis:
        from google.genai import types  # type: ignore[import-untyped]
        from PIL import Image as PILImage

        img = PILImage.open(image)
        response = self._client.models.generate_content(
            model=self._model,
            contents=[prompt, img],
            config=types.GenerateContentConfig(
                temperature=temperature or self._temperature,
                max_output_tokens=self._max_output_tokens,
            ),
        )
        return _parse_vision_response(response.text)


def _parse_vision_response(raw: str) -> VisionAnalysis:
    data: dict[str, Any] = parse_gemini_json(raw)

    frame_rate = max(8, min(24, int(data["frame_rate"])))
    frame_count = max(9, min(81, int(data.get("frame_count", 33))))
    min_motion = max(0.02, min(0.25, float(data["min_motion"])))
    max_motion = max(min_motion + 0.05, min(1.00, float(data["max_motion"])))
    max_diff = max(max_motion, min(1.50, float(data["max_diff"])))

    positive = data["positive"].strip()
    negative = data["negative"].strip()
    if len(positive) < 10 or len(negative) < 10:
        raise ValueError(f"Prompts too short (pos={len(positive)}, neg={len(negative)})")

    raw_zone = data.get("moving_zone", [0.0, 0.0, 1.0, 1.0])
    moving_zone = _clamp_zone(raw_zone)

    return VisionAnalysis(
        object_desc=data["object_desc"], action_desc=data["action_desc"],
        moving_parts=data.get("moving_parts", ""), fixed_parts=data.get("fixed_parts", ""),
        moving_zone=moving_zone, reason=data.get("reason", ""),
        frame_rate=frame_rate, frame_count=frame_count,
        min_motion=min_motion, max_motion=max_motion, max_diff=max_diff,
        positive=positive, negative=negative,
        pingpong=bool(data.get("pingpong", True)),
        bg_type=data.get("bg_type", "solid"), bg_remove=bool(data.get("bg_remove", True)),
    )


def _clamp_zone(raw_zone: list[Any]) -> list[float]:
    try:
        z = [float(v) for v in raw_zone[:4]]
        x1, y1 = max(0.0, min(1.0, z[0])), max(0.0, min(1.0, z[1]))
        x2, y2 = max(0.0, min(1.0, z[2])), max(0.0, min(1.0, z[3]))
        if x2 - x1 < 0.15:
            cx = (x1 + x2) / 2
            x1, x2 = max(0.0, cx - 0.075), min(1.0, cx + 0.075)
        if y2 - y1 < 0.15:
            cy = (y1 + y2) / 2
            y1, y2 = max(0.0, cy - 0.075), min(1.0, cy + 0.075)
        return [round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3)]
    except Exception:
        return [0.0, 0.0, 1.0, 1.0]
