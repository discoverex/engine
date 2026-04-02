"""PostMotionClassificationPort implementation — Gemini Vision Stage 2 classifier."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from discoverex.domain.animate import (
    MotionTravelType,
    PostMotionResult,
    TravelDirection,
)

from .gemini_common import GeminiClientMixin
from .gemini_post_motion_prompt import POST_MOTION_PROMPT

logger = logging.getLogger(__name__)


class GeminiPostMotionClassifier(GeminiClientMixin):
    """Stage 2: Determine keyframe travel type after WAN generation."""

    def __init__(self, model: str = "gemini-2.5-flash", max_retries: int = 2) -> None:
        super().__init__(model=model, max_retries=max_retries, temperature=0.1, max_output_tokens=2000)

    def classify(self, video: Path, original_image: Path) -> PostMotionResult:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._gemini_analyze(video, original_image)
            except Exception as e:
                last_error = e
                logger.warning(f"[Stage2] attempt {attempt}/{self._max_retries} failed: {e}")
                if attempt < self._max_retries:
                    time.sleep(2)

        logger.warning(f"[Stage2] all failed -> NO_TRAVEL fallback: {last_error}")
        return PostMotionResult(
            needs_keyframe=False,
            reason=f"Gemini failed -> no_travel fallback ({last_error})",
        )

    def _gemini_analyze(self, video: Path, original_image: Path) -> PostMotionResult:
        from google.genai import types  # type: ignore[import-untyped]
        from PIL import Image as PILImage

        original_img = None
        try:
            original_img = PILImage.open(original_image).convert("RGB")
        except Exception:
            logger.warning("[Stage2] original image load failed, video-only analysis")

        with open(video, "rb") as f:
            video_bytes = f.read()

        if len(video_bytes) < 18 * 1024 * 1024:
            video_part = types.Part(
                inline_data=types.Blob(data=video_bytes, mime_type="video/mp4")
            )
        else:
            uploaded = self._client.files.upload(
                file=str(video), config=types.UploadFileConfig(mime_type="video/mp4"),
            )
            while uploaded.state.name == "PROCESSING":
                time.sleep(2)
                uploaded = self._client.files.get(name=uploaded.name)
            video_part = types.Part(
                file_data=types.FileData(file_uri=uploaded.uri, mime_type="video/mp4")
            )

        contents: list[Any] = [POST_MOTION_PROMPT]
        if original_img:
            contents.extend(["Original reference image:", original_img])
        contents.extend(["Generated animation video:", video_part])

        response = self._client.models.generate_content(
            model=self._model, contents=contents,
            config=types.GenerateContentConfig(
                temperature=self._temperature, max_output_tokens=self._max_output_tokens,
            ),
        )
        return _parse_post_motion(response.text)


def _parse_post_motion(raw: str) -> PostMotionResult:
    clean = re.sub(r"```json|```", "", raw).strip()

    try:
        data: dict[str, Any] = json.loads(clean)
    except json.JSONDecodeError:
        repaired = clean
        if repaired.count('"') % 2 != 0:
            repaired += '"'
        open_b = repaired.count('{') - repaired.count('}')
        repaired += '}' * max(0, open_b)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            data = _extract_from_text(raw)

    needs_kf = bool(data.get("needs_keyframe", False))
    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
    if confidence < 0.5:
        needs_kf = False

    try:
        travel_type = MotionTravelType(data.get("travel_type", "no_travel"))
    except ValueError:
        travel_type = MotionTravelType.NO_TRAVEL

    if travel_type == MotionTravelType.NO_TRAVEL:
        needs_kf = False
    if not needs_kf:
        travel_type = MotionTravelType.NO_TRAVEL

    try:
        direction = TravelDirection(data.get("travel_direction", "none"))
    except ValueError:
        direction = TravelDirection.NONE
    if not needs_kf:
        direction = TravelDirection.NONE

    suggested = data.get("suggested_keyframe", "")
    if not suggested and needs_kf:
        suggested = {
            MotionTravelType.AMPLIFY_HOP: "hop",
            MotionTravelType.AMPLIFY_SWAY: "wobble",
            MotionTravelType.AMPLIFY_FLOAT: "float",
            MotionTravelType.TRAVEL_LATERAL: "nudge_horizontal",
            MotionTravelType.TRAVEL_VERTICAL: "nudge_vertical",
            MotionTravelType.TRAVEL_DIAGONAL: "nudge_horizontal",
        }.get(travel_type, "")

    return PostMotionResult(
        needs_keyframe=needs_kf, travel_type=travel_type,
        travel_direction=direction, confidence=confidence,
        reason=data.get("reason", ""), suggested_keyframe=suggested,
    )


def _extract_from_text(raw: str) -> dict[str, Any]:
    raw_lower = raw.lower()
    needs_kf = "true" in raw_lower.split("needs_keyframe")[1][:20] if "needs_keyframe" in raw_lower else False
    travel = "no_travel"
    for t in ["amplify_hop", "amplify_sway", "amplify_float", "travel_lateral", "travel_vertical", "travel_diagonal"]:
        if t in raw_lower:
            travel = t
            break
    direction = "none"
    for d in ["left", "right", "up", "down"]:
        if f'"{d}"' in raw_lower:
            direction = d
            break
    return {"needs_keyframe": needs_kf, "travel_type": travel, "travel_direction": direction, "confidence": 0.3, "suggested_keyframe": "", "reason": "parsed from incomplete response"}
