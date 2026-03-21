from __future__ import annotations

from typing import Any

from discoverex.settings import AppSettings


def resolve_config(
    config: AppSettings | dict[str, Any] | None,
) -> AppSettings:
    if config is None:
        raise ValueError("config must not be None")
    if isinstance(config, AppSettings):
        return config
    if isinstance(config, dict) and "pipeline" in config:
        return AppSettings.model_validate(config)
    raise TypeError("runtime context requires resolved AppSettings")
