"""AIValidationPort implementation — Gemini Vision subjective quality review."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from discoverex.domain.animate import AIValidationContext, AIValidationFix

from .gemini_ai_prompt import AI_VALIDATOR_SYSTEM_PROMPT
from .gemini_common import GeminiClientMixin

logger = logging.getLogger(__name__)


class GeminiAIValidator(GeminiClientMixin):
    """Gemini Vision subjective quality assessment with parameter fixes."""

    def __init__(self, model: str = "gemini-2.5-flash", max_retries: int = 2) -> None:
        super().__init__(model=model, max_retries=max_retries, temperature=0.2, max_output_tokens=4000)

    def validate(
        self, video: Path, original_image: Path, context: AIValidationContext,
    ) -> AIValidationFix:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._gemini_validate(video, original_image, context)
            except Exception as e:
                last_error = e
                logger.warning(f"[AIValidator] attempt {attempt}/{self._max_retries} failed: {e}")
                if attempt < self._max_retries:
                    time.sleep(2)

        logger.warning(f"[AIValidator] all failed -> fail result: {last_error}")
        return AIValidationFix(
            passed=False, issues=["ai_validator_error"],
            reason=f"AI validation failed ({last_error})",
        )

    def _gemini_validate(
        self, video: Path, original_image: Path, context: AIValidationContext,
    ) -> AIValidationFix:
        from google.genai import types  # type: ignore[import-untyped]
        from PIL import Image as PILImage

        original_img = PILImage.open(original_image).convert("RGB")

        with open(video, "rb") as f:
            video_bytes = f.read()

        ctx_text = (
            f"Current parameters: fps={context.current_fps}, scale={context.current_scale}\n"
            f"Current positive prompt: {context.positive}\n"
            f"Current negative prompt: {context.negative}\n\n"
            f"Please review the animation quality carefully."
        )

        if len(video_bytes) < 18 * 1024 * 1024:
            video_part = types.Part(
                inline_data=types.Blob(data=video_bytes, mime_type="video/mp4")
            )
        else:
            uploaded = self._client.files.upload(
                file=str(video),
                config=types.UploadFileConfig(mime_type="video/mp4"),
            )
            while uploaded.state.name == "PROCESSING":
                time.sleep(2)
                uploaded = self._client.files.get(name=uploaded.name)
            video_part = types.Part(
                file_data=types.FileData(file_uri=uploaded.uri, mime_type="video/mp4")
            )

        response = self._client.models.generate_content(
            model=self._model,
            contents=[AI_VALIDATOR_SYSTEM_PROMPT, ctx_text, original_img, video_part],
            config=types.GenerateContentConfig(
                temperature=self._temperature, max_output_tokens=self._max_output_tokens,
            ),
        )
        return _parse_ai_response(response.text)


def _parse_ai_response(raw: str) -> AIValidationFix:
    clean = re.sub(r"```json|```", "", raw).strip()

    try:
        data: dict[str, Any] = json.loads(clean)
    except json.JSONDecodeError:
        recovered = re.sub(r'"reason"\s*:\s*"(?:[^"\\]|\\.)*"', '"reason": ""', clean, flags=re.DOTALL)
        try:
            data = json.loads(recovered)
        except json.JSONDecodeError:
            passed_m = re.search(r'"passed"\s*:\s*(true|false)', clean)
            issues_m = re.search(r'"issues"\s*:\s*(\[[^\]]*\])', clean)
            data = {
                "passed": (passed_m.group(1) == "true") if passed_m else True,
                "issues": json.loads(issues_m.group(1)) if issues_m else [],
                "adjustments": {},
            }

    adj = data.get("adjustments", {})
    fr = adj.get("frame_rate")
    sc = adj.get("scale")
    if fr is not None:
        fr = max(10, min(24, int(fr)))
    if sc is not None:
        sc = max(0.40, min(0.80, float(sc)))

    return AIValidationFix(
        passed=bool(data.get("passed", True)),
        issues=data.get("issues", []),
        reason=data.get("reason", ""),
        frame_rate=fr, scale=sc,
        positive=adj.get("positive_addition"), negative=adj.get("negative_addition"),
    )
