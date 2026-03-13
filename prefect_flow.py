from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import traceback
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Any

from prefect import flow, get_run_logger
from prefect.context import get_run_context
from prefect.runtime import flow_run

_SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

_INPUTS_KEYS = ("inputs", "engine_run")
_ARTIFACT_DIR_ENV = "ORCH_ENGINE_ARTIFACT_DIR"
_ARTIFACT_MANIFEST_ENV = "ORCH_ENGINE_ARTIFACT_MANIFEST_PATH"
_DEFAULT_STAGE = "launcher_start"
_MAX_STAGE_LINES = 400


@dataclass
class LauncherExecution:
    returncode: int
    stdout: str
    stderr: str
    progress_events: list[dict[str, Any]] = field(default_factory=list)
    stage_logs: dict[str, str] = field(default_factory=dict)
    last_stage: str = _DEFAULT_STAGE


def _parse_progress_event(line: str) -> dict[str, Any] | None:
    candidate = line.strip()
    if not candidate.startswith("[discoverex-progress] "):
        return None
    payload = candidate.removeprefix("[discoverex-progress] ").strip()
    if not payload:
        return None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded


@flow(name="disoverex-engine-flow", retries=0)
def run_job_flow(
    job_spec_json: str,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    logger = get_run_logger()
    try:
        job_spec = _load_job_spec(job_spec_json)
        payload = _extract_inputs_payload(job_spec)
        env = _build_child_env(
            job_spec=job_spec,
            payload=payload,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
        )
        run_summary = _summarize_run_request(
            job_spec=job_spec,
            payload=payload,
            env=env,
            resume_key=resume_key,
            checkpoint_dir=checkpoint_dir,
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
        execution = _run_launcher_process(
            cmd=[
                sys.executable,
                "-m",
                "discoverex.orchestrator_contract.launcher",
            ],
            cwd=_repo_root(),
            env=env,
            logger=logger,
        )
        flow_run_id = flow_run.get_id() or "unknown-flow-run"
        attempt = _flow_attempt()
        local_paths = _write_local_artifacts(
            env=env,
            job_spec=job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
            returncode=execution.returncode,
            stdout=execution.stdout,
            stderr=execution.stderr,
        )
        uploaded = _upload_worker_artifacts(
            flow_run_id=flow_run_id,
            attempt=attempt,
            local_paths=local_paths,
            exit_code=execution.returncode,
            logger=logger,
        )
        if execution.returncode != 0:
            raise RuntimeError(
                _build_launcher_error(
                    execution.returncode,
                    execution.stdout,
                    execution.stderr,
                    progress_event=execution.progress_events[-1]
                    if execution.progress_events
                    else None,
                    failed_stage=execution.last_stage,
                    stage_log=execution.stage_logs.get(execution.last_stage, ""),
                )
            )
        parsed = _parse_json_result(execution.stdout)
        parsed.setdefault("job_name", _string_value(job_spec.get("job_name")))
        parsed.setdefault("engine", _string_value(job_spec.get("engine")))
        parsed.setdefault("run_mode", _string_value(job_spec.get("run_mode")))
        parsed.setdefault("flow_run_id", flow_run_id)
        parsed.setdefault("attempt", attempt)
        parsed.setdefault(
            "outputs_prefix",
            _outputs_prefix(job_spec, flow_run_id=flow_run_id, attempt=attempt),
        )
        parsed.setdefault("last_stage", execution.last_stage)
        if execution.progress_events:
            parsed.setdefault("progress_last_event", execution.progress_events[-1])
            logger.info(
                "launcher progress summary: %s",
                json.dumps(
                    _summarize_progress_event(execution.progress_events[-1]),
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            )
        parsed.update(uploaded)
        _raise_if_failed_payload(parsed)
        logger.info(
            "launcher payload summary: %s",
            json.dumps(_summarize_payload(parsed), sort_keys=True),
        )
        return parsed
    except Exception:
        failure_summary = {
            "repo_root": str(_repo_root()),
            "python_executable": sys.executable,
            "resume_key": _string_value(resume_key),
            "checkpoint_dir": _string_value(checkpoint_dir),
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


def _run_launcher_process(
    *,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    logger: Any,
) -> LauncherExecution:
    proc = Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=PIPE,
        stderr=PIPE,
        bufsize=1,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    progress_events: list[dict[str, Any]] = []
    stage_logs: dict[str, deque[str]] = {
        _DEFAULT_STAGE: deque(maxlen=_MAX_STAGE_LINES)
    }
    current_stage = _DEFAULT_STAGE
    stage_lock = threading.Lock()

    def record_stage_line(stage: str, line: str) -> None:
        text = line.rstrip("\n")
        if not text:
            return
        stage_logs.setdefault(stage, deque(maxlen=_MAX_STAGE_LINES)).append(text)

    def consume(stream: Any, *, stream_name: str, target: list[str]) -> None:
        nonlocal current_stage
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            target.append(line)
            event = _parse_progress_event(line)
            if event is not None:
                progress_events.append(event)
                stage = _string_value(event.get("stage")) or _DEFAULT_STAGE
                with stage_lock:
                    current_stage = stage
                    stage_logs.setdefault(stage, deque(maxlen=_MAX_STAGE_LINES))
                logger.info(
                    "stage %s %s",
                    stage,
                    _string_value(event.get("status")) or "updated",
                )
                continue
            with stage_lock:
                active_stage = current_stage
            record_stage_line(active_stage, f"[{stream_name}] {line.rstrip()}")
        stream.close()

    stdout_thread = threading.Thread(
        target=consume,
        args=(proc.stdout,),
        kwargs={"stream_name": "stdout", "target": stdout_lines},
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=consume,
        args=(proc.stderr,),
        kwargs={"stream_name": "stderr", "target": stderr_lines},
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    returncode = proc.wait()
    stdout_thread.join()
    stderr_thread.join()
    return LauncherExecution(
        returncode=returncode,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
        progress_events=progress_events,
        stage_logs={key: "\n".join(value) for key, value in stage_logs.items() if value},
        last_stage=current_stage,
    )


def _summarize_progress_event(event: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "stage",
        "status",
        "mode",
        "region_id",
        "index",
        "total",
        "candidate_count",
        "image_ref",
        "scene_id",
        "version_id",
        "passed",
        "total_score",
        "failed_stage",
    )
    return {key: event[key] for key in keys if key in event}


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


def _build_child_env(
    *,
    job_spec: dict[str, Any],
    payload: dict[str, Any],
    resume_key: str | None,
    checkpoint_dir: str | None,
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(_coerce_env_map(job_spec.get("env")))
    env["ORCH_JOB_INPUTS_JSON"] = json.dumps(job_spec, ensure_ascii=True)
    _ensure_worker_artifact_env(env)
    py_path = str(_repo_root() / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = py_path if not existing else f"{py_path}:{existing}"
    _set_if_value(env, "ORCH_ENGINE", job_spec.get("engine"))
    _set_if_value(env, "ORCH_RUN_MODE", job_spec.get("run_mode"))
    _set_if_value(env, "ORCH_JOB_NAME", job_spec.get("job_name"))
    _set_if_value(env, "ORCH_RESUME_KEY", resume_key)
    _set_if_value(env, "ORCH_CHECKPOINT_DIR", checkpoint_dir)
    return env


def _flow_attempt() -> int:
    try:
        ctx = get_run_context()
        return int(getattr(ctx.flow_run, "run_count", None) or 1)
    except Exception:
        return 1


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
    artifact_dir = Path(
        tempfile.mkdtemp(prefix="run-", dir=str(base_dir))
    ).resolve()
    manifest_path = artifact_dir / "engine-artifacts.json"
    env[_ARTIFACT_DIR_ENV] = str(artifact_dir)
    env[_ARTIFACT_MANIFEST_ENV] = str(manifest_path)


def _write_local_artifacts(
    *,
    env: dict[str, str],
    job_spec: dict[str, Any],
    flow_run_id: str,
    attempt: int,
    returncode: int,
    stdout: str,
    stderr: str,
) -> dict[str, str]:
    artifact_dir = Path(env[_ARTIFACT_DIR_ENV]).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    result_path = artifact_dir / "result.json"
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    result_payload = {
        "flow_run_id": flow_run_id,
        "attempt": attempt,
        "engine": _string_value(job_spec.get("engine")),
        "run_mode": _string_value(job_spec.get("run_mode")),
        "job_name": _string_value(job_spec.get("job_name")),
        "entrypoint": job_spec.get("entrypoint", []),
        "outputs_prefix": _outputs_prefix(
            job_spec,
            flow_run_id=flow_run_id,
            attempt=attempt,
        ),
        "exit_code": int(returncode),
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
    exit_code: int,
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
        require_manifest=exit_code == 0,
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


def _set_if_value(env: dict[str, str], key: str, value: object) -> None:
    text = _string_value(value)
    if text:
        env[key] = text


def _string_value(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _parse_json_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return {"status": "completed"}


def _summarize_run_request(
    *,
    job_spec: dict[str, Any],
    payload: dict[str, Any],
    env: dict[str, str],
    resume_key: str | None,
    checkpoint_dir: str | None,
) -> dict[str, Any]:
    runtime = payload.get("runtime", {})
    runtime_env = runtime.get("extra_env", {}) if isinstance(runtime, dict) else {}
    env_presence = {
        "artifact_dir": bool(env.get(_ARTIFACT_DIR_ENV, "").strip()),
        "artifact_manifest": bool(env.get(_ARTIFACT_MANIFEST_ENV, "").strip()),
        "orch_job_inputs_json": bool(env.get("ORCH_JOB_INPUTS_JSON", "").strip()),
        "mlflow_tracking_uri": bool(
            str(runtime_env.get("MLFLOW_TRACKING_URI", "")).strip()
        ),
        "mlflow_tracking_proxy_url": bool(
            os.getenv("MLFLOW_TRACKING_PROXY_URL", "").strip()
        ),
    }
    return {
        "engine": _string_value(job_spec.get("engine")),
        "run_mode": _string_value(job_spec.get("run_mode")),
        "job_name": _string_value(job_spec.get("job_name")),
        "command": _string_value(payload.get("command")),
        "config_name": _string_value(payload.get("config_name")),
        "config_dir": _string_value(payload.get("config_dir")),
        "repo_root": str(_repo_root()),
        "python_executable": sys.executable,
        "resume_key": _string_value(resume_key),
        "checkpoint_dir": _string_value(checkpoint_dir),
        "runtime_mode": _string_value(runtime.get("mode")) if isinstance(runtime, dict) else "",
        "runtime_extras": runtime.get("extras", []) if isinstance(runtime, dict) else [],
        "override_count": len(payload.get("overrides", []))
        if isinstance(payload.get("overrides", []), list)
        else 0,
        "env_presence": env_presence,
    }


def _build_launcher_error(
    returncode: int,
    stdout: str,
    stderr: str,
    *,
    progress_event: dict[str, Any] | None = None,
    failed_stage: str = "",
    stage_log: str = "",
) -> str:
    details: list[str] = [f"launcher exited with status code {returncode}"]
    if failed_stage:
        details.append(f"failed stage: {failed_stage}")
    if progress_event:
        details.append(
            "last progress event:\n"
            + json.dumps(
                _summarize_progress_event(progress_event),
                ensure_ascii=True,
                sort_keys=True,
            )
        )
    stage_log_tail = _tail_text(stage_log)
    if stage_log_tail:
        details.append(f"stage log dump:\n{stage_log_tail}")
    else:
        stdout_tail = _tail_text(stdout)
        stderr_tail = _tail_text(stderr)
        if stdout_tail:
            details.append(f"stdout tail:\n{stdout_tail}")
        if stderr_tail:
            details.append(f"stderr tail:\n{stderr_tail}")
    return "\n\n".join(details)


def _raise_if_failed_payload(parsed: dict[str, Any]) -> None:
    status = _string_value(parsed.get("status")).lower()
    if status not in {"failed", "error"}:
        return
    reason = _string_value(parsed.get("failure_reason")) or "child payload reported failure"
    raise RuntimeError(
        "launcher returned failed payload"
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


def _tail_text(raw: str, *, limit: int = 4000) -> str:
    text = raw.strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"...\n{text[-limit:]}"


__all__ = ["run_job_flow"]
