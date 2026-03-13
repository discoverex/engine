from __future__ import annotations

import importlib
import json
from typing import Any

INPUTS_KEYS = ("inputs", "engine_run")


def load_job_spec(job_spec_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(job_spec_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid job_spec_json: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("job_spec_json must decode to a JSON object")
    return payload


def extract_inputs_payload(job_spec: dict[str, Any]) -> dict[str, Any]:
    for key in INPUTS_KEYS:
        payload = job_spec.get(key)
        if payload is None:
            continue
        if not isinstance(payload, dict):
            raise RuntimeError(f"{key} must be a JSON object")
        return payload
    raise RuntimeError("job_spec_json requires inputs")


def dispatch_engine_job(payload: dict[str, Any]) -> dict[str, Any]:
    run_engine_entry = load_run_engine_entry()
    return run_engine_entry(
        command=mapped_command(string_value(payload.get("command"))),
        args=coerce_args(payload.get("args")),
        config_name=config_name(payload),
        config_dir=string_value(payload.get("config_dir")) or "conf",
        overrides=coerce_overrides(payload.get("overrides")),
    )


def load_run_engine_entry() -> Any:
    module = importlib.import_module("discoverex.application.flows.engine_entry")
    return getattr(module, "run_engine_entry")


def mapped_command(command: str) -> str:
    mapped = {
        "gen-verify": "generate",
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }.get(command)
    if mapped is None:
        raise RuntimeError(f"unsupported command={command or '<empty>'}")
    return mapped


def config_name(payload: dict[str, Any]) -> str:
    explicit = string_value(payload.get("config_name"))
    if explicit:
        return explicit
    command = string_value(payload.get("command"))
    defaults = {
        "gen-verify": "gen_verify",
        "verify-only": "verify_only",
        "replay-eval": "replay_eval",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }
    return defaults.get(command, command)


def coerce_args(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RuntimeError("inputs.args must be a JSON object")
    return dict(raw)


def coerce_overrides(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuntimeError("inputs.overrides must be a JSON array")
    return [str(item) for item in raw]


def string_value(value: object) -> str:
    return str(value).strip() if value is not None else ""
