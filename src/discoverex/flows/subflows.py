from __future__ import annotations

from typing import Any

from discoverex.application.use_cases import run_replay_eval
from discoverex.bootstrap import build_context
from discoverex.config import PipelineConfig

from .generate import run_generate_flow
from .verify import run_verify_flow


def generate_v1_compat(*, args: dict[str, Any], config: PipelineConfig) -> dict[str, str]:
    return run_generate_flow(args=args, config=config)


def verify_v1_compat(*, args: dict[str, Any], config: PipelineConfig) -> dict[str, str]:
    return run_verify_flow(args=args, config=config)


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
