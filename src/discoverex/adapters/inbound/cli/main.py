from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

import typer

from discoverex.application.contracts.execution.schema import JobRuntime
from discoverex.application.flows import build_inline_job_spec, run_engine_job
from discoverex.bootstrap import build_validator_context
from discoverex.config_loader import load_validator_config
from discoverex.runtime_logging import configure_logging, format_seconds, get_logger

app = typer.Typer(no_args_is_help=True)
logger = get_logger("discoverex.cli")


def _echo_json(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))


def _warn_legacy_command(legacy: str, replacement: str) -> None:
    typer.echo(
        f"[discoverex-cli] '{legacy}' is deprecated; use '{replacement}'",
        err=True,
    )


def _validate_generate_inputs(
    background_asset_ref: str | None,
    background_prompt: str | None,
) -> None:
    if (background_asset_ref or "").strip() or (background_prompt or "").strip():
        return
    raise typer.BadParameter(
        "either --background-asset-ref or --background-prompt is required"
    )


def _run_command(
    *,
    command: str,
    args: dict[str, object],
    config_name: str,
    config_dir: str,
    overrides: list[str],
) -> dict[str, object]:
    job_spec = build_inline_job_spec(
        command=command,
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        runtime=JobRuntime(mode="local"),
    )
    return run_engine_job(job_spec)


@app.command("generate")
def generate_command(
    background_asset_ref: str | None = typer.Option(None, "--background-asset-ref"),
    background_prompt: str | None = typer.Option(None, "--background-prompt"),
    background_negative_prompt: str | None = typer.Option(
        None, "--background-negative-prompt"
    ),
    object_prompt: str | None = typer.Option(None, "--object-prompt"),
    object_negative_prompt: str | None = typer.Option(None, "--object-negative-prompt"),
    final_prompt: str | None = typer.Option(None, "--final-prompt"),
    final_negative_prompt: str | None = typer.Option(None, "--final-negative-prompt"),
    config_name: str = typer.Option("generate", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    _validate_generate_inputs(background_asset_ref, background_prompt)
    configure_logging(verbose=verbose)
    started = perf_counter()
    logger.info(
        "generate command started background_prompt=%s object_prompt=%s final_prompt=%s",
        bool((background_prompt or "").strip()),
        bool((object_prompt or "").strip()),
        bool((final_prompt or "").strip()),
    )
    payload = _run_command(
        command="generate",
        args={
            key: value
            for key, value in {
                "background_asset_ref": background_asset_ref,
                "background_prompt": background_prompt,
                "background_negative_prompt": background_negative_prompt,
                "object_prompt": object_prompt,
                "object_negative_prompt": object_negative_prompt,
                "final_prompt": final_prompt,
                "final_negative_prompt": final_negative_prompt,
            }.items()
            if value is not None
        },
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    logger.info("generate command completed in %s", format_seconds(started))
    _echo_json(payload)


@app.command("verify")
def verify_command(
    scene_json: str = typer.Option(..., "--scene-json"),
    config_name: str = typer.Option("verify", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    configure_logging(verbose=verbose)
    payload = _run_command(
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
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    configure_logging(verbose=verbose)
    payload = _run_command(
        command="animate",
        args={"scene_jsons": scene_jsons},
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("gen-verify", hidden=True)
def gen_verify_legacy_command(
    background_asset_ref: str | None = typer.Option(None, "--background-asset-ref"),
    background_prompt: str | None = typer.Option(None, "--background-prompt"),
    background_negative_prompt: str | None = typer.Option(
        None, "--background-negative-prompt"
    ),
    object_prompt: str | None = typer.Option(None, "--object-prompt"),
    object_negative_prompt: str | None = typer.Option(None, "--object-negative-prompt"),
    final_prompt: str | None = typer.Option(None, "--final-prompt"),
    final_negative_prompt: str | None = typer.Option(None, "--final-negative-prompt"),
    config_name: str = typer.Option("gen_verify", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    _warn_legacy_command("gen-verify", "generate")
    _validate_generate_inputs(background_asset_ref, background_prompt)
    configure_logging(verbose=verbose)
    payload = _run_command(
        command="generate",
        args={
            key: value
            for key, value in {
                "background_asset_ref": background_asset_ref,
                "background_prompt": background_prompt,
                "background_negative_prompt": background_negative_prompt,
                "object_prompt": object_prompt,
                "object_negative_prompt": object_negative_prompt,
                "final_prompt": final_prompt,
                "final_negative_prompt": final_negative_prompt,
            }.items()
            if value is not None
        },
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
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    _warn_legacy_command("verify-only", "verify")
    configure_logging(verbose=verbose)
    payload = _run_command(
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
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    _warn_legacy_command("replay-eval", "animate")
    configure_logging(verbose=verbose)
    payload = _run_command(
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
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    configure_logging(verbose=verbose)
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
