from __future__ import annotations

from pathlib import Path

from prefect import flow

from discoverex.application.use_cases import (
    run_gen_verify,
    run_replay_eval,
    run_verify_only,
)
from discoverex.bootstrap import build_context
from discoverex.config_loader import load_pipeline_config
from discoverex.domain.scene import Scene


def _artifacts_root(config: dict[str, object]) -> str:
    runtime = config.get("runtime")
    if isinstance(runtime, dict):
        root = runtime.get("artifacts_root")
        if isinstance(root, str):
            return root
    return "artifacts"


@flow(name="discoverex-gen-verify", retries=2, retry_delay_seconds=3)
def gen_verify_flow(
    background_asset_ref: str,
    config_name: str = "gen_verify",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, str]:
    cfg = load_pipeline_config(
        config_name=config_name, config_dir=config_dir, overrides=overrides or []
    )
    context = build_context(config=cfg)
    scene = run_gen_verify(background_asset_ref=background_asset_ref, context=context)
    root = _artifacts_root(cfg)
    return {
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "scene_json": f"{root}/scenes/{scene.meta.scene_id}/{scene.meta.version_id}/scene.json",
    }


@flow(name="discoverex-verify-only", retries=2, retry_delay_seconds=3)
def verify_only_flow(
    scene_json_path: str,
    config_name: str = "verify_only",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, str]:
    cfg = load_pipeline_config(
        config_name=config_name, config_dir=config_dir, overrides=overrides or []
    )
    context = build_context(config=cfg)
    path = Path(scene_json_path)
    scene = Scene.model_validate_json(path.read_text(encoding="utf-8"))
    updated = run_verify_only(scene=scene, context=context)
    root = _artifacts_root(cfg)
    return {
        "scene_id": updated.meta.scene_id,
        "version_id": updated.meta.version_id,
        "status": updated.meta.status.value,
        "scene_json": f"{root}/scenes/{updated.meta.scene_id}/{updated.meta.version_id}/scene.json",
    }


@flow(name="discoverex-replay-eval")
def replay_eval_flow(
    scene_json_paths: list[str],
    config_name: str = "replay_eval",
    config_dir: str = "conf",
    overrides: list[str] | None = None,
) -> dict[str, str]:
    cfg = load_pipeline_config(
        config_name=config_name, config_dir=config_dir, overrides=overrides or []
    )
    context = build_context(config=cfg)
    report = run_replay_eval(scene_json_paths=scene_json_paths, context=context)
    return {"report": str(report)}
