from __future__ import annotations

import os

from discoverex.cache_dirs import (
    resolve_cache_root,
    resolve_model_cache_dir,
    resolve_uv_cache_dir,
)
from discoverex.runtime_logging import get_logger

logger = get_logger("discoverex.engine")


def log_runtime_env_diagnostics() -> None:
    cache_dir = os.getenv("CACHE_DIR", "").strip()
    model_cache_dir = os.getenv("MODEL_CACHE_DIR", "").strip()
    uv_cache_dir = os.getenv("UV_CACHE_DIR", "").strip()
    hf_home = os.getenv("HF_HOME", "").strip()
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    tracking_proxy = os.getenv("MLFLOW_TRACKING_PROXY_URL", "").strip()
    metadata_db_url = os.getenv("METADATA_DB_URL", "").strip()
    resolved_cache_root = resolve_cache_root().resolve()
    resolved_uv_cache = resolve_uv_cache_dir(default_base=resolved_cache_root).resolve()
    resolved_model_cache = resolve_model_cache_dir(default_base=resolved_cache_root).resolve()

    logger.info(
        "engine runtime env: cache_dir=%s uv_cache_dir=%s model_cache_dir=%s hf_home=%s mlflow_tracking_uri=%s mlflow_tracking_proxy=%s metadata_db_url=%s",
        cache_dir or str(resolved_cache_root),
        uv_cache_dir or str(resolved_uv_cache),
        model_cache_dir or str(resolved_model_cache),
        hf_home or "",
        tracking_uri or "",
        tracking_proxy or "",
        metadata_db_url or "",
    )
    if not cache_dir:
        logger.warning(
            "CACHE_DIR is not set; runtime will fall back to repo-local or user cache directories"
        )
    if not tracking_uri:
        logger.warning(
            "MLFLOW_TRACKING_URI is not set; runtime will fall back to config/default tracking storage"
        )
    elif tracking_uri.startswith(("http://", "https://")) and not tracking_proxy:
        logger.warning(
            "MLFLOW_TRACKING_URI is remote but MLFLOW_TRACKING_PROXY_URL is not set; worker launcher may reject remote tracking"
        )
    if not metadata_db_url:
        logger.info(
            "METADATA_DB_URL is not set; metadata storage will use the configured local/json fallback"
        )
