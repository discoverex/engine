from __future__ import annotations

from typing import Any

from discoverex.config import PipelineConfig
from discoverex.settings import AppSettings, coerce_settings


def resolve_config(
    config: AppSettings | PipelineConfig | dict[str, Any] | None,
) -> AppSettings:
    if config is None:
        raise ValueError("config must not be None")
    return coerce_settings(config)
