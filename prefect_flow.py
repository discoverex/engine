from __future__ import annotations

import json
import importlib
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.runtime import flow_run

_SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

_INPUTS_KEYS = ("inputs", "engine_run")
_ARTIFACT_DIR_ENV = "ORCH_ENGINE_ARTIFACT_DIR"
_ARTIFACT_MANIFEST_ENV = "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"
_FAILED_STATUSES = {"failed", "error"}


@flow(name="disoverex-engine-flow", retries=0)
def run_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    flow_run_id = flow_run.get_id() or "unknown-flow-run"
    attempt = _flow_attempt()
    try:
        job_spec = _load_job_spec(job_spec_json)
        payload = _extract_inputs_payload(job_spec)
        outputs_prefix = _outputs_prefix(
            job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
        )
        env = _build_runtime_env(
            job_spec=job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
            outputs_prefix=outputs_prefix,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
        )
        run_summary = _summarize_run_request(
            job_spec=job_spec,
            payload=payload,
            env=env,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
            outputs_prefix=outputs_prefix,
        )
        logger.info(
            "engine flow start: %s",
            json.dumps(run_summary, ensure_ascii=True, sort_keys=True),
        )
        print(
            "[discoverex-engine-flow] start "
            + json.dumps(run_summary, ensure_ascii=True, sort_keys=True),
            file=sys.stderr,
        )
        with _patched_environ(env):
            parsed = _dispatch_engine_job(payload)
        parsed.setdefault("job_name", _string_value(job_spec.get("job_name")))
        parsed.setdefault("engine", _string_value(job_spec.get("engine")))
        parsed.setdefault("run_mode", _string_value(job_spec.get("run_mode")))
        parsed.setdefault("flow_run_id", flow_run_id)
        parsed.setdefault("attempt", attempt)
        parsed.setdefault("outputs_prefix", outputs_prefix)
        local_paths = _write_local_artifacts(
            env=env,
            parsed=parsed,
            flow_run_id=flow_run_id,
            attempt=attempt,
            job_spec=job_spec,
        )
        uploaded = _upload_worker_artifacts(
            flow_run_id=flow_run_id,
            attempt=attempt,
            local_paths=local_paths,
            require_manifest=_payload_status(parsed) not in _FAILED_STATUSES,
            logger=logger,
        )
        parsed.update(uploaded)
        _raise_if_failed_payload(parsed)
        logger.info(
            "engine payload summary: %s",
            json.dumps(_summarize_payload(parsed), ensure_ascii=True, sort_keys=True),
        )
        return parsed
    except Exception:
        failure_summary = {
            "repo_root": str(_repo_root()),
            "python_executable": sys.executable,
            "resume_key": _string_value(resume_key),
            "checkpoint_dir": _string_value(checkpoint_dir),
            "flow_run_id": flow_run_id,
            "attempt": attempt,
        }
        logger.error(
            "engine flow failed before completion: %s",
            json.dumps(failure_summary, ensure_ascii=True, sort_keys=True),
        )
        print(
            "[discoverex-engine-flow] failure-context "
            + json.dumps(failure_summary, ensure_ascii=True, sort_keys=True),
            file=sys.stderr,
        )
        print(traceback.format_exc(), file=sys.stderr, end="")
        raise


def _dispatch_engine_job(payload: dict[str, Any]) -> dict[str, Any]:
    run_engine_entry = _load_run_engine_entry()
    return run_engine_entry(
        command=_mapped_command(_string_value(payload.get("command"))),
        args=_coerce_args(payload.get("args")),
        config_name=_config_name(payload),
        config_dir=_string_value(payload.get("config_dir")) or "conf",
        overrides=_coerce_overrides(payload.get("overrides")),
    )


def _load_run_engine_entry() -> Any:
    module = importlib.import_module("discoverex.application.flows.engine_entry")
    return getattr(module, "run_engine_entry")


def _mapped_command(command: str) -> str:
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


def _config_name(payload: dict[str, Any]) -> str:
    explicit = _string_value(payload.get("config_name"))
    if explicit:
        return explicit
    command = _string_value(payload.get("command"))
    defaults = {
        "gen-verify": "gen_verify",
        "verify-only": "verify_only",
        "replay-eval": "replay_eval",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }
    return defaults.get(command, command)


def _coerce_args(raw: object) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RuntimeError("inputs.args must be a JSON object")
    return dict(raw)


def _coerce_overrides(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuntimeError("inputs.overrides must be a JSON array")
    return [str(item) for item in raw]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _load_job_spec(job_spec_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(job_spec_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid job_spec_json: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("job_spec_json must decode to a JSON object")
    return payload


def _extract_inputs_payload(job_spec: dict[str, Any]) -> dict[str, Any]:
    for key in _INPUTS_KEYS:
        payload = job_spec.get(key)
        if payload is None:
            continue
        if not isinstance(payload, dict):
            raise RuntimeError(f"{key} must be a JSON object")
        return payload
    raise RuntimeError("job_spec_json requires inputs")


def _build_runtime_env(
    *,
    job_spec: dict[str, Any],
    flow_run_id: str,
    attempt: int,
    outputs_prefix: str,
    resume_key: str | None,
    checkpoint_dir: str | None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(_coerce_env_map(job_spec.get("env")))
    _ensure_worker_artifact_env(env)
    py_path = str(_repo_root() / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = py_path if not existing else f"{py_path}:{existing}"
    _set_if_value(env, "ORCH_ENGINE", job_spec.get("engine"))
    _set_if_value(env, "ORCH_RUN_MODE", job_spec.get("run_mode"))
    _set_if_value(env, "ORCH_JOB_NAME", job_spec.get("job_name"))
    _set_if_value(env, "ORCH_FLOW_RUN_ID", flow_run_id)
    env["ORCH_ATTEMPT"] = str(attempt)
    env["ORCH_OUTPUTS_PREFIX"] = outputs_prefix
    _set_if_value(env, "ORCH_RESUME_KEY", resume_key)
    _set_if_value(env, "ORCH_CHECKPOINT_DIR", checkpoint_dir)
    return env


def _coerce_env_map(raw: object) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RuntimeError("job_spec.env must be a JSON object")
    return {str(key): str(value) for key, value in raw.items()}


def _ensure_worker_artifact_env(env: dict[str, str]) -> None:
    if env.get(_ARTIFACT_DIR_ENV, "").strip() and env.get(
        _ARTIFACT_MANIFEST_ENV, ""
    ).strip():
        return
    base_dir = _repo_root() / ".prefect-engine-artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir = Path(tempfile.mkdtemp(prefix="run-", dir=str(base_dir))).resolve()
    env[_ARTIFACT_DIR_ENV] = str(artifact_dir)
    env[_ARTIFACT_MANIFEST_ENV] = str(artifact_dir / "engine-artifacts.json")


@contextmanager
def _patched_environ(updates: dict[str, str]) -> Iterator[None]:
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


def _flow_attempt() -> int:
    try:
        ctx = get_run_context()
        return int(getattr(ctx.flow_run, "run_count", None) or 1)
    except Exception:
        return 1


def _write_local_artifacts(
    *,
    env: dict[str, str],
    parsed: dict[str, Any],
    flow_run_id: str,
    attempt: int,
    job_spec: dict[str, Any],
) -> dict[str, str]:
    artifact_dir = Path(env[_ARTIFACT_DIR_ENV]).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    result_path = artifact_dir / "result.json"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    result_payload = {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "engine": _string_value(job_spec.get("engine")),
        "run_mode": _string_value(job_spec.get("run_mode")),
        "job_name": _string_value(job_spec.get("job_name")),
        "outputs_prefix": _outputs_prefix(
            job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
        ),
        "payload": parsed,
    }
    result_path.write_text(
        json.dumps(result_payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "result": str(result_path),
        "engine_artifact_dir": str(artifact_dir),
        "engine_artifact_manifest": str(Path(env[_ARTIFACT_MANIFEST_ENV]).resolve()),
    }


def _upload_worker_artifacts(
    *,
    flow_run_id: str,
    attempt: int,
    local_paths: dict[str, str],
    require_manifest: bool,
    logger: Any,
) -> dict[str, Any]:
    if not os.getenv("STORAGE_API_URL", "").strip():
        logger.info("storage upload skipped: STORAGE_API_URL not configured")
        return {}
    from discoverex.orchestrator_contract.output_uploads import (
        upload_engine_artifacts,
        upload_outputs,
    )

    uploaded = upload_outputs(
        flow_run_id=flow_run_id,
        attempt=attempt,
        local_paths=local_paths,
    )
    engine_uploaded = upload_engine_artifacts(
        flow_run_id=flow_run_id,
        attempt=attempt,
        local_paths=local_paths,
        require_manifest=require_manifest,
    )
    payload: dict[str, Any] = {
        "stdout_uri": uploaded.get("stdout"),
        "stderr_uri": uploaded.get("stderr"),
        "result_uri": uploaded.get("result"),
        "manifest_uri": uploaded.get("manifest"),
    }
    if engine_uploaded.manifest_uri:
        payload["engine_manifest_uri"] = engine_uploaded.manifest_uri
    if engine_uploaded.artifact_uris:
        payload["engine_artifact_uris"] = engine_uploaded.artifact_uris
    return {key: value for key, value in payload.items() if value}


def _outputs_prefix(
    job_spec: dict[str, Any],
    *,
    flow_run_id: str,
    attempt: int,
) -> str:
    raw = _string_value(job_spec.get("outputs_prefix"))
    if raw:
        return raw
    return f"jobs/{flow_run_id}/attempt-{attempt}/"


def _summarize_run_request(
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
    env_presence = {
        "artifact_dir": bool(env.get(_ARTIFACT_DIR_ENV, "").strip()),
        "artifact_manifest": bool(env.get(_ARTIFACT_MANIFEST_ENV, "").strip()),
        "mlflow_tracking_uri": bool(
            str(runtime_env.get("MLFLOW_TRACKING_URI", "")).strip()
        ),
    }
    return {
        "engine": _string_value(job_spec.get("engine")),
        "run_mode": _string_value(job_spec.get("run_mode")),
        "job_name": _string_value(job_spec.get("job_name")),
        "command": _string_value(payload.get("command")),
        "config_name": _config_name(payload),
        "config_dir": _string_value(payload.get("config_dir")) or "conf",
        "repo_root": str(_repo_root()),
        "python_executable": sys.executable,
        "resume_key": _string_value(resume_key),
        "checkpoint_dir": _string_value(checkpoint_dir),
        "outputs_prefix": outputs_prefix,
        "runtime_mode": (
            _string_value(runtime.get("mode")) if isinstance(runtime, dict) else ""
        ),
        "runtime_extras": (
            runtime.get("extras", []) if isinstance(runtime, dict) else []
        ),
        "override_count": len(_coerce_overrides(payload.get("overrides"))),
        "env_presence": env_presence,
    }


def _payload_status(parsed: dict[str, Any]) -> str:
    return _string_value(parsed.get("status")).lower() or "completed"


def _raise_if_failed_payload(parsed: dict[str, Any]) -> None:
    status = _payload_status(parsed)
    if status not in _FAILED_STATUSES:
        return
    reason = _string_value(parsed.get("failure_reason")) or (
        "engine payload reported failure"
    )
    raise RuntimeError(
        "engine flow returned failed payload"
        f"\n\nreason: {reason}"
        f"\n\npayload: {json.dumps(parsed, ensure_ascii=True, sort_keys=True)}"
    )


def _summarize_payload(parsed: dict[str, Any]) -> dict[str, str]:
    keys = (
        "status",
        "job_name",
        "engine",
        "run_mode",
        "scene_id",
        "version_id",
        "scene_json",
        "report",
        "execution_config",
        "stdout_uri",
        "stderr_uri",
        "result_uri",
        "manifest_uri",
        "engine_manifest_uri",
    )
    summary = {
        key: _string_value(parsed.get(key))
        for key in keys
        if _string_value(parsed.get(key))
    }
    if not summary:
        return {"status": "completed"}
    return summary


def _set_if_value(env: dict[str, str], key: str, value: object) -> None:
    text = _string_value(value)
    if text:
        env[key] = text


def _string_value(value: object) -> str:
    return str(value).strip() if value is not None else ""


__all__ = ["run_job_flow"]
