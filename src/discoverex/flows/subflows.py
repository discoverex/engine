from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.application.use_cases import (
    run_gen_verify,
    run_replay_eval,
    run_verify_only,
)
from discoverex.bootstrap import build_context
from discoverex.config import PipelineConfig
from discoverex.domain.scene import Scene


def _scene_payload(scene: Scene, root: str) -> dict[str, str]:
    return {
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "scene_json": f"{root}/scenes/{scene.meta.scene_id}/{scene.meta.version_id}/scene.json",
    }


def generate_v1_compat(*, args: dict[str, Any], config: PipelineConfig) -> dict[str, str]:
    background_asset_ref = str(args["background_asset_ref"])
    context = build_context(config=config)
    scene = run_gen_verify(background_asset_ref=background_asset_ref, context=context)
    return _scene_payload(scene, config.runtime.artifacts_root)


def verify_v1_compat(*, args: dict[str, Any], config: PipelineConfig) -> dict[str, str]:
    scene_json = str(args["scene_json"])
    scene = Scene.model_validate_json(Path(scene_json).read_text(encoding="utf-8"))
    context = build_context(config=config)
    updated = run_verify_only(scene=scene, context=context)
    return _scene_payload(updated, config.runtime.artifacts_root)


def animate_replay_eval(*, args: dict[str, Any], config: PipelineConfig) -> dict[str, str]:
    scene_jsons = [str(item) for item in args.get("scene_jsons", [])]
    context = build_context(config=config)
    report = run_replay_eval(scene_json_paths=scene_jsons, context=context)
    return {"report": str(report)}


def animate_stub(*, args: dict[str, Any], config: PipelineConfig) -> dict[str, Any]:
    _ = args
    _ = config
    return {
        "status": "failed",
        "failure_reason": "animate flow is not implemented yet",
        "metadata": {"stub": True},
    }
