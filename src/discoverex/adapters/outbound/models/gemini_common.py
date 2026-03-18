"""Shared Gemini Vision SDK utilities for animate pipeline adapters.

Centralizes google-genai client initialization and JSON response parsing
to avoid duplication across 4 Gemini adapters.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from discoverex.models.types import ModelHandle

logger = logging.getLogger(__name__)


class GeminiClientMixin:
    """Mixin providing load/unload lifecycle for Gemini Vision adapters.

    Adapter __init__ stores config; load() initializes the SDK client.
    """

    _client: Any
    _model: str
    _max_retries: int

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        max_retries: int = 3,
        temperature: float = 0.1,
        max_output_tokens: int = 2000,
    ) -> None:
        self._model_name = model
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client: Any = None
        self._model: str = model

    def load(self, handle: ModelHandle) -> None:
        api_key = handle.extra.get("api_key", "")
        if not api_key:
            raise ValueError("ModelHandle.extra must contain 'api_key'")
        from google import genai  # type: ignore[import-untyped]

        self._client = genai.Client(api_key=api_key)
        self._model = handle.extra.get("model", self._model_name)
        logger.info(f"[Gemini] client initialized: model={self._model}")

    def unload(self) -> None:
        self._client = None


def parse_gemini_json(raw: str) -> dict[str, Any]:
    """Parse Gemini response text as JSON with markdown fence cleanup."""
    clean = re.sub(r"```json|```", "", raw).strip()
    return json.loads(clean)  # type: ignore[no-any-return]
