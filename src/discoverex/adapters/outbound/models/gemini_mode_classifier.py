"""ModeClassificationPort implementation — Gemini Vision Stage 1 classifier."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from discoverex.domain.animate import (
    FacingDirection,
    ModeClassification,
    ProcessingMode,
)

from .gemini_common import GeminiClientMixin, parse_gemini_json
from .gemini_mode_fallback import extract_from_text
from .gemini_mode_prompt import MODE_CLASSIFIER_PROMPT

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = {"has_deformable_parts", "processing_mode"}


def _robust_parse(raw: str) -> dict[str, Any]:
    """3-stage JSON recovery for mode classifier responses."""
    import json
    import re

    # Stage 1: normal parse
    try:
        data = parse_gemini_json(raw)
        if _REQUIRED_KEYS & set(data.keys()):
            return data  # type: ignore[no-any-return]
    except (json.JSONDecodeError, ValueError):
        pass

    # Stage 2: quote/brace repair
    clean = re.sub(r"```json|```", "", raw).strip()
    repaired = clean
    if repaired.count('"') % 2 != 0:
        repaired += '"'
    open_b = repaired.count("{") - repaired.count("}")
    repaired += "}" * max(0, open_b)
    try:
        data = json.loads(repaired)
        if _REQUIRED_KEYS & set(data.keys()):
            return data  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # Stage 3: keyword extraction with rigid-body detection
    return extract_from_text(raw.lower())


class GeminiModeClassifier(GeminiClientMixin):
    """Stage 1: Determine KEYFRAME_ONLY vs MOTION_NEEDED via Gemini Vision."""

    def __init__(self, model: str = "gemini-2.5-flash", max_retries: int = 3) -> None:
        super().__init__(model=model, max_retries=max_retries, temperature=0.1, max_output_tokens=1000)

    def classify(self, image: Path) -> ModeClassification:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._gemini_classify(image)
            except Exception as e:
                last_error = e
                logger.warning(f"[Stage1] attempt {attempt}/{self._max_retries} failed: {e}")
                if attempt < self._max_retries:
                    time.sleep(2)

        logger.warning(f"[Stage1] all failed -> MOTION_NEEDED fallback: {last_error}")
        return ModeClassification(
            processing_mode=ProcessingMode.MOTION_NEEDED,
            has_deformable=True,
            subject_desc="classification failed",
            reason=f"Gemini failed -> MOTION_NEEDED fallback ({last_error})",
        )

    def _gemini_classify(self, image: Path) -> ModeClassification:
        from google.genai import types  # type: ignore[import-untyped]
        from PIL import Image as PILImage

        img = PILImage.open(image)
        response = self._client.models.generate_content(
            model=self._model,
            contents=[MODE_CLASSIFIER_PROMPT, img],
            config=types.GenerateContentConfig(
                temperature=self._temperature,
                max_output_tokens=self._max_output_tokens,
            ),
        )
        return _parse_mode_response(response.text)


def _parse_mode_response(raw: str) -> ModeClassification:
    data = _robust_parse(raw)

    if not data.get("is_classifiable", True):
        return ModeClassification(
            processing_mode=ProcessingMode.KEYFRAME_ONLY,
            has_deformable=False,
            subject_desc=data.get("subject_desc", "unclassifiable"),
            reason=data.get("reason", "pre-check failed"),
            suggested_action="pop",
        )

    is_scene = bool(data.get("is_scene", False))
    if "has_deformable_parts" in data:
        has_deformable = bool(data["has_deformable_parts"])
    elif data.get("processing_mode") == "keyframe_only":
        has_deformable = False
    else:
        has_deformable = True

    if is_scene:
        mode = ProcessingMode.MOTION_NEEDED
    elif has_deformable:
        mode = ProcessingMode.MOTION_NEEDED
    else:
        mode = ProcessingMode.KEYFRAME_ONLY

    try:
        facing = FacingDirection(data.get("facing_direction", "none"))
    except ValueError:
        facing = FacingDirection.NONE

    suggested_action = data.get("suggested_action", "")
    if mode != ProcessingMode.KEYFRAME_ONLY:
        suggested_action = ""
    elif not suggested_action:
        if facing == FacingDirection.NONE:
            suggested_action = "wobble"
        elif facing in (FacingDirection.UP, FacingDirection.DOWN):
            suggested_action = "nudge_vertical"
        else:
            suggested_action = "nudge_horizontal"

    return ModeClassification(
        processing_mode=mode,
        facing_direction=facing,
        has_deformable=has_deformable,
        is_scene=is_scene,
        subject_desc=data.get("subject_desc", ""),
        reason=data.get("reason", ""),
        suggested_action=suggested_action,
    )
