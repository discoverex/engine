from __future__ import annotations

from typing import Any

from discoverex.config import PipelineConfig


def resolve_config(config: PipelineConfig | dict[str, Any] | None) -> PipelineConfig:
    if config is None:
        raise ValueError("config must not be None")
    if isinstance(config, PipelineConfig):
        return config
    return PipelineConfig.model_validate(config)
