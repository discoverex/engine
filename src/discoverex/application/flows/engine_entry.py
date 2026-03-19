from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal, cast

from prefect import flow

from discoverex.runtime_logging import format_seconds, get_logger

from .common import build_error_payload

if TYPE_CHECKING:
    from discoverex.config import PipelineConfig

FlowCommand = Literal["generate", "verify", "animate"]
SubflowHandler = Callable[..., dict[str, Any]]
logger = get_logger("discoverex.engine")


def load_pipeline_config(
    config_name: str,
    config_dir: str = "conf",
    overrides: list[str] | None = None,
    resolved_config: object | None = None,
) -> "PipelineConfig":
    from discoverex.config_loader import (
        resolve_pipeline_config as _resolve_pipeline_config,
    )

    return _resolve_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )


def build_execution_snapshot(**kwargs: Any) -> dict[str, Any]:
    from discoverex.execution_snapshot import build_execution_snapshot as _build

    return _build(**kwargs)


def summarize_for_logging(snapshot: dict[str, Any]) -> dict[str, str]:
    from discoverex.execution_snapshot import summarize_for_logging as _summarize

    return _summarize(snapshot)


def write_execution_snapshot(**kwargs: Any) -> Path:
    from discoverex.execution_snapshot import write_execution_snapshot as _write

    return _write(**kwargs)


def normalize_pipeline_config_for_worker_runtime(config: Any) -> Any:
    from discoverex.orchestrator_contract.worker_runtime import (
        normalize_pipeline_config_for_worker_runtime as _normalize,
    )

    return _normalize(config)


def _log_runtime_env_diagnostics() -> None:
    model_cache_dir = os.getenv("MODEL_CACHE_DIR", "").strip()
    hf_home = os.getenv("HF_HOME", "").strip()
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    tracking_proxy = os.getenv("MLFLOW_TRACKING_PROXY_URL", "").strip()
    metadata_db_url = os.getenv("METADATA_DB_URL", "").strip()

    logger.info(
        "engine runtime env: model_cache_dir=%s hf_home=%s mlflow_tracking_uri=%s mlflow_tracking_proxy=%s metadata_db_url=%s",
        bool(model_cache_dir),
        bool(hf_home),
        bool(tracking_uri),
        bool(tracking_proxy),
        bool(metadata_db_url),
    )
    if not model_cache_dir:
        logger.warning(
            "MODEL_CACHE_DIR is not set; model adapters will fall back to HF_HOME or a user cache directory"
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


def _resolve_subflow(config: "PipelineConfig", command: FlowCommand) -> SubflowHandler:
    from hydra.utils import instantiate

    if config.flows is None:
        raise ValueError("flows config is required for engine entry flow")
    component = getattr(config.flows, command)
    handler = instantiate(component.as_kwargs())
    return cast(SubflowHandler, handler)


def engine_entry_flow(
    command: FlowCommand,
    args: dict[str, Any],
    config_name: str,
    config_dir: str = "conf",
    overrides: list[str] | None = None,
    resolved_config: object | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    logger.info(
        "engine entry started command=%s config_name=%s overrides=%d",
        command,
        config_name,
        len(overrides or []),
    )
    _log_runtime_env_diagnostics()
    cfg = load_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides or [],
        resolved_config=resolved_config,
    )
    cfg = normalize_pipeline_config_for_worker_runtime(cfg)
    execution_snapshot = build_execution_snapshot(
        command=command,
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides or [],
        config=cfg,
    )
    execution_config_path = write_execution_snapshot(
        artifacts_root=Path(cfg.runtime.artifacts_root).resolve(),
        command=command,
        snapshot=execution_snapshot,
    )
    summary = summarize_for_logging(execution_snapshot)
    logger.info(
        "engine entry resolved command=%s config_name=%s tracker=%s artifact_store=%s device=%s",
        summary["command"],
        summary["config_name"],
        summary["tracker"],
        summary["artifact_store"],
        summary["device"],
    )
    subflow = _resolve_subflow(cfg, command)
    try:
        payload = subflow(
            args=args,
            config=cfg,
            execution_snapshot=execution_snapshot,
            execution_snapshot_path=execution_config_path,
        )
        payload.setdefault("execution_config", str(execution_config_path))
        logger.info(
            "engine entry completed command=%s in %s",
            command,
            format_seconds(started),
        )
        return payload
    except Exception as exc:
        logger.exception(
            "engine entry failed command=%s after %s",
            command,
            format_seconds(started),
        )
        return build_error_payload(
            command=command,
            args=args,
            exc=exc,
            execution_config_path=str(execution_config_path),
        )


def run_engine_entry(
    command: FlowCommand,
    args: dict[str, Any],
    config_name: str,
    config_dir: str = "conf",
    overrides: list[str] | None = None,
    resolved_config: object | None = None,
) -> dict[str, Any]:
    return engine_entry_flow(
        command=command,
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )


@flow(name="discoverex-engine-entry-pipeline", persist_result=False)
def run_prefect_engine_entry_flow(
    command: FlowCommand,
    args: dict[str, Any],
    config_name: str,
    config_dir: str = "conf",
    overrides: list[str] | None = None,
    resolved_config: object | None = None,
) -> dict[str, Any]:
    return engine_entry_flow(
        command=command,
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )
