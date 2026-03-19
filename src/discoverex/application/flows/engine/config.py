from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from discoverex.config import PipelineConfig


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


def normalize_pipeline_config_for_worker_runtime(config: Any) -> Any:
    from discoverex.orchestrator_contract.worker_runtime import (
        normalize_pipeline_config_for_worker_runtime as _normalize,
    )

    return _normalize(config)
