from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Literal, cast

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
) -> "PipelineConfig":
    from discoverex.config_loader import load_pipeline_config as _load_pipeline_config

    return _load_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
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
) -> dict[str, Any]:
    started = perf_counter()
    logger.info(
        "engine entry started command=%s config_name=%s overrides=%d",
        command,
        config_name,
        len(overrides or []),
    )
    cfg = load_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides or [],
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
) -> dict[str, Any]:
    return engine_entry_flow(
        command=command,
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
    )
