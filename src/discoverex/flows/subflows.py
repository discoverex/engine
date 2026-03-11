from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.application.use_cases import run_replay_eval
from discoverex.bootstrap import build_context
from discoverex.config import PipelineConfig

from .generate import run_generate_flow
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
    scene_jsons = [str(item) for item in args.get("scene_jsons", [])]
    context = build_context(
        config=config,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )
    report = run_replay_eval(scene_json_paths=scene_jsons, context=context)
    payload = {"report": str(report)}
    if execution_snapshot_path is not None:
        payload["execution_config"] = str(execution_snapshot_path)
    return payload


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
