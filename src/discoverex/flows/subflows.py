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
    if getattr(context, "tracking_run_id", None):
        payload["mlflow_run_id"] = str(context.tracking_run_id)
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


def animate_pipeline(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    """Animate pipeline flow — orchestrates sprite animation generation."""
    from discoverex.bootstrap.factory import build_animate_context

    image_path = args.get("image_path", "")
    if not image_path:
        return {
            "status": "failed",
            "failure_reason": "image_path is required",
            **(
                {"execution_config": str(execution_snapshot_path)}
                if execution_snapshot_path is not None
                else {}
            ),
        }

    # PipelineConfig strips animate-specific keys (extra="ignore").
    # Re-compose raw Hydra config to preserve animate models/adapters.
    if execution_snapshot and execution_snapshot.get("config_name"):
        from discoverex.config_loader import load_raw_animate_config

        raw_config = load_raw_animate_config(
            config_name=execution_snapshot["config_name"],
            config_dir=execution_snapshot.get("config_dir", "conf"),
            overrides=execution_snapshot.get("overrides", []),
        )
    else:
        raw_config = config.model_dump()
    orchestrator = build_animate_context(raw_config)
    result = orchestrator.run(Path(image_path))

    payload: dict[str, Any] = {
        "status": "success" if result.success else "failed",
    }
    if result.video_path:
        payload["video_path"] = str(result.video_path)
    if result.analysis:
        payload["action"] = result.analysis.action_desc
    if result.mode:
        payload["mode"] = result.mode.processing_mode.value
    payload["attempts"] = result.attempts
    if execution_snapshot_path is not None:
        payload["execution_config"] = str(execution_snapshot_path)
    return payload
