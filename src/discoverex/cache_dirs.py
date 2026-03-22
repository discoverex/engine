from __future__ import annotations

import os
from pathlib import Path


def resolve_cache_root(
    *,
    default_base: Path | None = None,
    cache_dir: str = "",
    model_cache_dir: str = "",
) -> Path:
    if cache_dir.strip():
        return Path(cache_dir).expanduser()
    if model_cache_dir.strip():
        return Path(model_cache_dir).expanduser()
    env_model_cache_dir = os.getenv("MODEL_CACHE_DIR", "").strip()
    if env_model_cache_dir:
        return Path(env_model_cache_dir).expanduser()
    env_hf_home = os.getenv("HF_HOME", "").strip()
    if env_hf_home:
        return Path(env_hf_home).expanduser().parent
    if default_base is not None:
        return default_base
    return Path.cwd() / ".cache"


def resolve_uv_cache_dir(
    *,
    default_base: Path | None = None,
    uv_cache_dir: str = "",
    cache_dir: str = "",
    model_cache_dir: str = "",
) -> Path:
    if uv_cache_dir.strip():
        return Path(uv_cache_dir).expanduser()
    return resolve_cache_root(
        default_base=default_base,
        cache_dir=cache_dir,
        model_cache_dir=model_cache_dir,
    ) / "uv"


def resolve_model_cache_dir(
    *,
    default_base: Path | None = None,
    model_cache_dir: str = "",
    cache_dir: str = "",
) -> Path:
    if model_cache_dir.strip():
        return Path(model_cache_dir).expanduser()
    return resolve_cache_root(
        default_base=default_base,
        cache_dir=cache_dir,
        model_cache_dir=model_cache_dir,
    ) / "models"
