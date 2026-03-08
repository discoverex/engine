from __future__ import annotations

from pathlib import Path
from typing import Any

from prefect import flow, task

from discoverex.application.use_cases import run_verify_only
from discoverex.bootstrap import build_context
from discoverex.config import PipelineConfig
from discoverex.domain.scene import Scene

from .common import build_scene_payload


@task(name="discoverex-verify-load-scene", persist_result=False)
def _load_scene(scene_json: str) -> Scene:
    return Scene.model_validate_json(Path(scene_json).read_text(encoding="utf-8"))


@task(name="discoverex-verify-context", persist_result=False)
def _build_context(config: PipelineConfig) -> Any:
    return build_context(config=config)


@task(name="discoverex-verify-usecase", persist_result=False)
def _run_verify_only(scene: Scene, context: Any) -> Scene:
    return run_verify_only(scene=scene, context=context)


@flow(name="discoverex-verify-pipeline", persist_result=False)
def run_verify_flow(*, args: dict[str, Any], config: PipelineConfig) -> dict[str, str]:
    scene_json = str(args["scene_json"])
    scene = _load_scene(scene_json)
    context = _build_context(config)
    updated = _run_verify_only(scene, context)
    return build_scene_payload(updated, config.runtime.artifacts_root)
