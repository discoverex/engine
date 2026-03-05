from __future__ import annotations

import json
from pathlib import Path

import typer

from discoverex.application.use_cases import (
    run_gen_verify,
    run_replay_eval,
    run_verify_only,
)
from discoverex.bootstrap import build_context, build_validator_context
from discoverex.config import PipelineConfig
from discoverex.config_loader import load_pipeline_config, load_validator_config
from discoverex.domain.scene import Scene

app = typer.Typer(no_args_is_help=True)


def _resolve_config(
    config_name: str, config_dir: str, overrides: list[str] | None
) -> PipelineConfig:
    return load_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides or [],
    )


def _artifacts_root(config: PipelineConfig) -> str:
    return config.runtime.artifacts_root


@app.command("gen-verify")
def gen_verify_command(
    background_asset_ref: str = typer.Option(..., "--background-asset-ref"),
    config_name: str = typer.Option("gen_verify", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    config = _resolve_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    context = build_context(config=config)
    scene = run_gen_verify(background_asset_ref=background_asset_ref, context=context)
    root = _artifacts_root(config)
    payload = {
        "scene_id": scene.meta.scene_id,
        "version_id": scene.meta.version_id,
        "status": scene.meta.status.value,
        "scene_json": f"{root}/scenes/{scene.meta.scene_id}/{scene.meta.version_id}/scene.json",
    }
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command("verify-only")
def verify_only_command(
    scene_json: str = typer.Option(..., "--scene-json"),
    config_name: str = typer.Option("verify_only", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    config = _resolve_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    scene_path = Path(scene_json)
    scene = Scene.model_validate_json(scene_path.read_text(encoding="utf-8"))
    context = build_context(config=config)
    updated = run_verify_only(scene=scene, context=context)
    root = _artifacts_root(config)
    payload = {
        "scene_id": updated.meta.scene_id,
        "version_id": updated.meta.version_id,
        "status": updated.meta.status.value,
        "scene_json": f"{root}/scenes/{updated.meta.scene_id}/{updated.meta.version_id}/scene.json",
    }
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command("replay-eval")
def replay_eval_command(
    scene_jsons: list[str] = typer.Option(..., "--scene-jsons"),
    config_name: str = typer.Option("replay_eval", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    config = _resolve_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    context = build_context(config=config)
    report_path = run_replay_eval(scene_json_paths=scene_jsons, context=context)
    typer.echo(json.dumps({"report": str(report_path)}, ensure_ascii=False))


@app.command("validate")
def validate_command(
    composite_image: Path = typer.Argument(..., help="Path to the composite scene image"),
    object_layer: list[Path] = typer.Option(
        ..., "--object-layer", help="Object layer PNG (repeat per object)"
    ),
    config_name: str = typer.Option("validator", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    """Run the 4-phase Validator pipeline on a composite image.

    Output JSON: {"status", "pass", "total_score", "perception_score",
                  "logical_score", "answer_obj_count", "failure_reason"}
    """
    config = load_validator_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    orchestrator = build_validator_context(config=config)
    bundle = orchestrator.run(
        composite_image=composite_image, object_layers=object_layer
    )
    payload = {
        "status": "pass" if bundle.final.pass_ else "fail",
        "pass": bundle.final.pass_,
        "total_score": round(bundle.final.total_score, 4),
        "perception_score": round(bundle.perception.score, 4),
        "logical_score": round(bundle.logical.score, 4),
        "answer_obj_count": bundle.logical.signals.get("answer_obj_count", 0),
        "failure_reason": bundle.final.failure_reason,
    }
    typer.echo(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    app()
