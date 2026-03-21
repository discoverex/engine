from __future__ import annotations

from pathlib import Path
from typing import Any

from prefect import flow, task

from discoverex.application.services.runtime import require_resolved_settings
from discoverex.application.use_cases import run_verify_only
from discoverex.bootstrap import build_context
from discoverex.config import PipelineConfig
from discoverex.domain.scene import Scene
from discoverex.settings import AppSettings

from .common import build_scene_payload


@task(name="discoverex-verify-load-scene", persist_result=False)
def _load_scene(scene_json: str) -> Scene:
    return Scene.model_validate_json(Path(scene_json).read_text(encoding="utf-8"))


@task(name="discoverex-verify-context", persist_result=False)
def _build_context(
    settings: AppSettings,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> Any:
    return build_context(
        settings=settings,
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
    )


@task(name="discoverex-verify-usecase", persist_result=False)
def _run_verify_only(scene: Scene, context: Any) -> Scene:
    return run_verify_only(scene=scene, context=context)


@flow(name="discoverex-verify-pipeline", persist_result=False)
def run_verify_flow(
    *,
    args: dict[str, Any],
    config: PipelineConfig,
    execution_snapshot: dict[str, Any] | None = None,
    execution_snapshot_path: Path | None = None,
) -> dict[str, str]:
    settings = require_resolved_settings(execution_snapshot, consumer="verify flow")
    scene_json = str(args["scene_json"])
    scene = _load_scene.submit(scene_json).result()
    context = _build_context.submit(
        settings,
        execution_snapshot,
        execution_snapshot_path,
    ).result()
    updated = _run_verify_only.submit(scene, context).result()
    return build_scene_payload(
        updated,
        artifacts_root=config.runtime.artifacts_root,
        execution_config_path=execution_snapshot_path,
        mlflow_run_id=getattr(context, "tracking_run_id", None),
        effective_tracking_uri=settings.tracking.uri,
        flow_run_id=settings.execution.flow_run_id,
    )
