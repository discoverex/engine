from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from prefect.context import get_run_context

from infra.prefect.bootstrap import repo_root
from infra.prefect.job_spec import coerce_overrides, config_name, string_value

ARTIFACT_DIR_ENV = "ORCH_ENGINE_ARTIFACT_DIR"
ARTIFACT_MANIFEST_ENV = "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"


def build_runtime_env(
    *,
    job_spec: dict[str, Any],
    flow_run_id: str,
    attempt: int,
    outputs_prefix: str,
    resume_key: str | None,
    checkpoint_dir: str | None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(coerce_env_map(job_spec.get("env")))
    ensure_worker_artifact_env(env)
    py_path = str(repo_root() / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = py_path if not existing else f"{py_path}:{existing}"
    set_if_value(env, "ORCH_ENGINE", job_spec.get("engine"))
    set_if_value(env, "ORCH_RUN_MODE", job_spec.get("run_mode"))
    set_if_value(env, "ORCH_JOB_NAME", job_spec.get("job_name"))
    set_if_value(env, "ORCH_FLOW_RUN_ID", flow_run_id)
    env["ORCH_ATTEMPT"] = str(attempt)
    env["ORCH_OUTPUTS_PREFIX"] = outputs_prefix
    set_if_value(env, "ORCH_RESUME_KEY", resume_key)
    set_if_value(env, "ORCH_CHECKPOINT_DIR", checkpoint_dir)
    return env


def coerce_env_map(raw: object) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RuntimeError("job_spec.env must be a JSON object")
    return {str(key): str(value) for key, value in raw.items()}


def ensure_worker_artifact_env(env: dict[str, str]) -> None:
    if (
        env.get(ARTIFACT_DIR_ENV, "").strip()
        and env.get(ARTIFACT_MANIFEST_ENV, "").strip()
    ):
        return
    base_dir = repo_root() / ".prefect-engine-artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(tempfile.mkdtemp(prefix="run-", dir=str(base_dir))).resolve()
    env[ARTIFACT_DIR_ENV] = str(artifact_dir)
    env[ARTIFACT_MANIFEST_ENV] = str(artifact_dir / "engine-artifacts.json")


@contextmanager
def patched_environ(updates: dict[str, str]) -> Iterator[None]:
    before = {key: os.environ.get(key) for key in updates}
    os.environ.update(updates)
    try:
        yield None
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def flow_attempt() -> int:
    try:
        ctx = get_run_context()
        flow_run_ctx = getattr(ctx, "flow_run", None)
        return int(getattr(flow_run_ctx, "run_count", None) or 1)
    except Exception:
        return 1


def outputs_prefix(
    job_spec: dict[str, Any],
    *,
    flow_run_id: str,
    attempt: int,
) -> str:
    raw = string_value(job_spec.get("outputs_prefix"))
    if raw:
        return raw
    return f"jobs/{flow_run_id}/attempt-{attempt}/"


def summarize_run_request(
    *,
    job_spec: dict[str, Any],
    payload: dict[str, Any],
    env: dict[str, str],
    resume_key: str | None,
    checkpoint_dir: str | None,
    outputs_prefix: str,
) -> dict[str, Any]:
    runtime = payload.get("runtime", {})
    runtime_env = runtime.get("extra_env", {}) if isinstance(runtime, dict) else {}
    resolved_config = redact_resolved_config(payload)
    env_presence = {
        "artifact_dir": bool(env.get(ARTIFACT_DIR_ENV, "").strip()),
        "artifact_manifest": bool(env.get(ARTIFACT_MANIFEST_ENV, "").strip()),
        "mlflow_tracking_uri": bool(
            str(runtime_env.get("MLFLOW_TRACKING_URI", "")).strip()
        ),
    }
    return {
        "engine": string_value(job_spec.get("engine")),
        "run_mode": string_value(job_spec.get("run_mode")),
        "job_name": string_value(job_spec.get("job_name")),
        "command": string_value(payload.get("command")),
        "config_name": config_name(payload),
        "config_dir": string_value(payload.get("config_dir")) or "conf",
        "repo_root": str(repo_root()),
        "python_executable": sys.executable,
        "resume_key": string_value(resume_key),
        "checkpoint_dir": string_value(checkpoint_dir),
        "outputs_prefix": outputs_prefix,
        "runtime_mode": (
            string_value(runtime.get("mode")) if isinstance(runtime, dict) else ""
        ),
        "runtime_extras": (
            runtime.get("extras", []) if isinstance(runtime, dict) else []
        ),
        "resolved_config": resolved_config,
        "override_count": len(coerce_overrides(payload.get("overrides"))),
        "env_presence": env_presence,
    }


def redact_resolved_config(payload: dict[str, Any]) -> Any:
    _ensure_repo_src_on_syspath()
    from discoverex.config_loader import resolve_pipeline_config
    from discoverex.execution_snapshot import redact_for_logging

    resolved_config = payload.get("resolved_config")
    if resolved_config is None:
        resolved_config = resolve_pipeline_config(
            config_name=config_name(payload),
            config_dir=string_value(payload.get("config_dir")) or "conf",
            overrides=coerce_overrides(payload.get("overrides")),
        ).model_dump(mode="python")
    return redact_for_logging(resolved_config)


def _ensure_repo_src_on_syspath() -> None:
    src_dir = repo_root() / "src"
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def set_if_value(env: dict[str, str], key: str, value: object) -> None:
    text = string_value(value)
    if text:
        env[key] = text
