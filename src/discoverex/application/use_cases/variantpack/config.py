from __future__ import annotations

# mypy: ignore-errors
from pathlib import Path
from typing import Any

from discoverex.application.flows.engine_entry import (
    build_execution_snapshot,
    load_pipeline_config,
    normalize_pipeline_config_for_worker_runtime,
    write_execution_snapshot,
)
from discoverex.config import PipelineConfig


def variant_config(
    *,
    base_snapshot: dict[str, Any] | None,
    variant_overrides: list[str],
    fallback_config: PipelineConfig,
) -> tuple[PipelineConfig, dict[str, Any], Path]:
    if base_snapshot is None:
        raise ValueError("execution_snapshot is required for variant pack flow")
    config_name = str(base_snapshot.get("config_name", "generate") or "generate")
    config_dir = str(base_snapshot.get("config_dir", "conf") or "conf")
    base_overrides = base_snapshot.get("overrides", [])
    if not isinstance(base_overrides, list):
        base_overrides = []
    merged_overrides = [str(item) for item in base_overrides] + variant_overrides
    cfg = load_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=merged_overrides,
    )
    cfg = normalize_pipeline_config_for_worker_runtime(cfg)
    cfg.runtime.artifacts_root = fallback_config.runtime.artifacts_root
    snapshot = build_execution_snapshot(
        command="generate",
        args={},
        config_name=config_name,
        config_dir=config_dir,
        overrides=merged_overrides,
        config=cfg,
    )
    snapshot_path = write_execution_snapshot(
        artifacts_root=Path(cfg.runtime.artifacts_root).resolve(),
        command="generate",
        snapshot=snapshot,
    )
    return cfg, snapshot, snapshot_path
