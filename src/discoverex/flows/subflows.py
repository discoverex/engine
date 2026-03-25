from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.application.services.runtime import (
    build_report_payload,
    require_resolved_settings,
)
from discoverex.application.use_cases import run_replay_eval
from discoverex.application.use_cases.generate_object_only import (
    run as run_generate_object_only,
)
from discoverex.application.use_cases.generate_single_object_debug import (
    run as run_generate_single_object_debug,
)
from discoverex.application.use_cases.generate_verify_v2 import (
    run as run_generate_verify_v2,
)
from discoverex.bootstrap import build_context
from discoverex.config import PipelineConfig

from .generate import run_generate_flow
from .generate_variant_pack import run_generate_inpaint_variant_pack_flow
from .verify import run_verify_flow


def generate_v1_compat(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, str]:
    return run_generate_flow(
        args=args,
        config=config,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )


def generate_v2_compat(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, str]:
    return run_generate_flow(
        args=args,
        config=config,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )


def generate_verify_v2(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, str]:
    settings = require_resolved_settings(
        execution_snapshot,
        consumer="generate_verify_v2",
    )
    context = build_context(
        settings=settings,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )
    return run_generate_verify_v2(
        args=args,
        config=config,
        context=context,
        execution_snapshot_path=execution_snapshot_path,
    )


def generate_object_only(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    settings = require_resolved_settings(
        execution_snapshot,
        consumer="generate_object_only",
    )
    context = build_context(
        settings=settings,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )
    return run_generate_object_only(
        args=args,
        config=config,
        context=context,
        execution_snapshot_path=execution_snapshot_path,
    )


def generate_single_object_debug(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    settings = require_resolved_settings(
        execution_snapshot,
        consumer="generate_single_object_debug",
    )
    context = build_context(
        settings=settings,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )
    return run_generate_single_object_debug(
        args=args,
        config=config,
        context=context,
        execution_snapshot_path=execution_snapshot_path,
    )


def generate_inpaint_variant_pack(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    return run_generate_inpaint_variant_pack_flow(
        args=args,
        config=config,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )


def verify_v1_compat(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, str]:
    return run_verify_flow(
        args=args,
        config=config,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )


def animate_replay_eval(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, str]:
    settings = require_resolved_settings(
        execution_snapshot,
        consumer="animate_replay_eval",
    )
    scene_jsons = [str(item) for item in args.get("scene_jsons", [])]
    context = build_context(
        settings=settings,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )
    report = run_replay_eval(scene_json_paths=scene_jsons, context=context)
    return build_report_payload(
        report=report,
        settings=settings,
        execution_config_path=execution_snapshot_path,
        tracking_run_id=getattr(context, "tracking_run_id", None),
    )


def animate_stub(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    _ = args
    _ = config
    _ = execution_snapshot
    return {
        "status": "failed",
        "failure_reason": "animate flow is not implemented yet",
        "metadata": {"stub": True},
        **(
            {"execution_config": str(execution_snapshot_path)}
            if execution_snapshot_path is not None
            else {}
        ),
    }
