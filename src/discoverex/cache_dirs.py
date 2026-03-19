from __future__ import annotations

import os
from pathlib import Path


def resolve_cache_root(*, default_base: Path | None = None) -> Path:
    cache_dir = os.getenv("CACHE_DIR", "").strip()
    if cache_dir:
        return Path(cache_dir).expanduser()
    model_cache_dir = os.getenv("MODEL_CACHE_DIR", "").strip()
    if model_cache_dir:
        return Path(model_cache_dir).expanduser()
    if default_base is not None:
        return default_base
    return Path.cwd() / ".cache"


def resolve_uv_cache_dir(*, default_base: Path | None = None) -> Path:
    explicit = os.getenv("UV_CACHE_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return resolve_cache_root(default_base=default_base) / "uv"


def resolve_model_cache_dir(*, default_base: Path | None = None) -> Path:
    explicit = os.getenv("MODEL_CACHE_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return resolve_cache_root(default_base=default_base) / "models"
