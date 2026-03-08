from __future__ import annotations

import json
from pathlib import Path

import typer

from discoverex.bootstrap import build_validator_context
from discoverex.config_loader import load_validator_config
from discoverex.flows import run_engine_entry

app = typer.Typer(no_args_is_help=True)


def _echo_json(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))


def _warn_legacy_command(legacy: str, replacement: str) -> None:
    typer.echo(
        f"[discoverex-cli] '{legacy}' is deprecated; use '{replacement}'",
        err=True,
    )


@app.command("generate")
def generate_command(
    background_asset_ref: str = typer.Option(..., "--background-asset-ref"),
    config_name: str = typer.Option("generate", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    payload = run_engine_entry(
        command="generate",
        args={"background_asset_ref": background_asset_ref},
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("verify")
def verify_command(
    scene_json: str = typer.Option(..., "--scene-json"),
    config_name: str = typer.Option("verify", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    payload = run_engine_entry(
        command="verify",
        args={"scene_json": scene_json},
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("animate")
def animate_command(
    scene_jsons: list[str] = typer.Option([], "--scene-jsons"),
    config_name: str = typer.Option("animate", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    payload = run_engine_entry(
        command="animate",
        args={"scene_jsons": scene_jsons},
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("gen-verify", hidden=True)
def gen_verify_legacy_command(
    background_asset_ref: str = typer.Option(..., "--background-asset-ref"),
    config_name: str = typer.Option("gen_verify", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    _warn_legacy_command("gen-verify", "generate")
    payload = run_engine_entry(
        command="generate",
        args={"background_asset_ref": background_asset_ref},
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("verify-only", hidden=True)
def verify_only_legacy_command(
    scene_json: str = typer.Option(..., "--scene-json"),
    config_name: str = typer.Option("verify_only", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    _warn_legacy_command("verify-only", "verify")
    payload = run_engine_entry(
        command="verify",
        args={"scene_json": scene_json},
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("replay-eval", hidden=True)
def replay_eval_legacy_command(
    scene_jsons: list[str] = typer.Option(..., "--scene-jsons"),
    config_name: str = typer.Option("replay_eval", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
    _warn_legacy_command("replay-eval", "animate")
    payload = run_engine_entry(
        command="animate",
        args={"scene_jsons": scene_jsons},
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("validate")
def validate_command(
    composite_image: Path = typer.Argument(
        ..., help="Path to the composite scene image"
    ),
    object_layer: list[Path] = typer.Option(
        ..., "--object-layer", help="Object layer PNG (repeat per object)"
    ),
    config_name: str = typer.Option("validator", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
) -> None:
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
    _echo_json(payload)


if __name__ == "__main__":
    app()
