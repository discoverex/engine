from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from prefect import flow

from discoverex.runtime_logging import format_seconds, get_logger

from .common import build_error_payload
from .engine import (
    FlowCommand,
    build_execution_snapshot,
    load_pipeline_config,
    log_runtime_env_diagnostics,
    normalize_pipeline_config_for_worker_runtime,
    summarize_for_logging,
    write_execution_snapshot,
)
from .engine import (
    resolve_subflow as _resolve_subflow,
)

logger = get_logger("discoverex.engine")


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
    log_runtime_env_diagnostics()
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
    return run_engine_entry(
        command=command,
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )
