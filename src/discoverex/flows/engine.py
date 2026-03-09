from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, cast
from time import perf_counter

from hydra.utils import instantiate
from prefect import flow

from discoverex.config import PipelineConfig
from discoverex.config_loader import load_pipeline_config
from discoverex.flows.common import build_error_payload
from discoverex.runtime_logging import format_seconds, get_logger

FlowCommand = Literal["generate", "verify", "animate"]
SubflowHandler = Callable[..., dict[str, Any]]
logger = get_logger("discoverex.engine")


def _resolve_subflow(config: PipelineConfig, command: FlowCommand) -> SubflowHandler:
    if config.flows is None:
        raise ValueError("flows config is required for engine entry flow")
    component = getattr(config.flows, command)
    handler = instantiate(component.as_kwargs())
    return cast(SubflowHandler, handler)


@flow(name="discoverex-engine-entry", retries=2, retry_delay_seconds=3)
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
    subflow = _resolve_subflow(cfg, command)
    try:
        payload = subflow(args=args, config=cfg)
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
        return build_error_payload(command=command, args=args, exc=exc)


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
