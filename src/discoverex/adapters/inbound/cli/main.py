from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import typer

from discoverex.application.contracts.execution.schema import JobRuntime
from discoverex.application.flows.run_engine_job import (
    build_inline_job_spec,
    run_engine_job,
)
from discoverex.bootstrap import build_validator_context
from discoverex.config_loader import load_validator_config
from discoverex.runtime_logging import configure_logging, format_seconds, get_logger

app = typer.Typer(no_args_is_help=True)
logger = get_logger("discoverex.cli")


def _echo_json(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))


def _run_e2e(
    *,
    scenario: str,
    model_group: str,
    work_dir: str | None,
    ensure_live_infra: bool,
) -> dict[str, object]:
    e2e_module = _load_e2e_module()
    ensure_e2e_live_infra = e2e_module.ensure_live_infra
    run_live_services_e2e = e2e_module.run_live_services_e2e
    run_tracking_artifact_e2e = e2e_module.run_tracking_artifact_e2e
    run_worker_contract_e2e = e2e_module.run_worker_contract_e2e

    if work_dir:
        target_dir = Path(work_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = Path(".cache/discoverex/e2e").resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
    if ensure_live_infra:
        ensure_e2e_live_infra()

    summaries: dict[str, object] = {}
    if scenario in {"tracking-artifact", "all"}:
        summaries["tracking-artifact"] = _e2e_summary_dict(
            run_tracking_artifact_e2e(work_dir=target_dir, model_group=model_group)
        )
    if scenario in {"worker-contract", "all"}:
        summaries["worker-contract"] = _e2e_summary_dict(
            run_worker_contract_e2e(work_dir=target_dir, model_group=model_group)
        )
    if scenario in {"live-services", "all"}:
        summaries["live-services"] = _e2e_summary_dict(
            run_live_services_e2e(work_dir=target_dir, model_group=model_group)
        )
    return summaries


def _e2e_summary_dict(summary: Any) -> dict[str, object]:
    return {
        "scenario": str(summary.scenario),
        "work_dir": str(summary.work_dir),
        "scene_id": str(summary.scene_id),
        "version_id": str(summary.version_id),
        "scene_json": str(summary.scene_json),
        "verification_json": str(summary.verification_json),
        "execution_config": str(summary.execution_config),
        "extra": cast(dict[str, object], summary.extra),
    }


def _load_e2e_module() -> Any:
    try:
        from infra.e2e import engine_runtime_e2e as module
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[5]
        module_path = repo_root / "infra" / "e2e" / "engine_runtime_e2e.py"
        repo_root_text = str(repo_root)
        if repo_root_text not in sys.path:
            sys.path.insert(0, repo_root_text)
        spec = importlib.util.spec_from_file_location(
            "discoverex_engine_runtime_e2e",
            module_path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"failed to load e2e module: {module_path}"
            ) from None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


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
    return cast(dict[str, object], run_engine_job(job_spec))


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
    image_path: str = typer.Option("", "--image-path", help="Input image for animation"),
    scene_jsons: list[str] = typer.Option([], "--scene-jsons"),
    config_name: str = typer.Option("animate", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    configure_logging(verbose=verbose)
    args: dict[str, object] = {"scene_jsons": scene_jsons}
    if image_path:
        args["image_path"] = image_path
    payload = _run_command(
        command="animate",
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=override,
    )
    _echo_json(payload)


@app.command("serve")
def serve_command(
    port: int = typer.Option(5001, "--port", help="Server port"),
    host: str = typer.Option("0.0.0.0", "--host", help="Server host"),
    config_name: str = typer.Option("animate_comfyui", "--config-name"),
    config_dir: str = typer.Option("conf", "--config-dir"),
    override: list[str] = typer.Option([], "--override", "-o"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    """Start animate dashboard web server."""
    configure_logging(verbose=verbose)
    from discoverex.adapters.inbound.web.engine_server import create_app
    from discoverex.bootstrap.factory import build_animate_context
    from discoverex.config_loader import load_raw_animate_config

    raw_config = load_raw_animate_config(
        config_name=config_name, config_dir=config_dir, overrides=override,
    )
    orchestrator = build_animate_context(raw_config)
    flask_app = create_app(orchestrator)
    typer.echo(f"Dashboard: http://{host}:{port}/")
    flask_app.run(host=host, port=port, debug=verbose)


@app.command("e2e")
def e2e_command(
    scenario: str = typer.Option(
        "all",
        "--scenario",
        help="One of: tracking-artifact, worker-contract, live-services, all",
    ),
    model_group: str = typer.Option("tiny_torch", "--model-group"),
    work_dir: str | None = typer.Option(None, "--work-dir"),
    ensure_live_infra: bool = typer.Option(False, "--ensure-live-infra"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    if scenario not in {"tracking-artifact", "worker-contract", "live-services", "all"}:
        raise typer.BadParameter(
            "scenario must be one of: tracking-artifact, worker-contract, live-services, all"
        )
    configure_logging(verbose=verbose)
    payload = _run_e2e(
        scenario=scenario,
        model_group=model_group,
        work_dir=work_dir,
        ensure_live_infra=ensure_live_infra,
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
