from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, cast
from urllib import error, request
from urllib.parse import urlencode, urlsplit


class MLflowTrackerAdapter:
    def __init__(
        self,
        experiment_name: str = "discoverex-core",
        tracking_uri: str = "sqlite:///mlflow.db",
        artifact_bucket: str = "discoverex-artifacts",
        cf_access_client_id: str = "",
        cf_access_client_secret: str = "",
        **_: str,
    ) -> None:
        self._mlflow: Any | None = None
        self._tracking_uri = tracking_uri
        self._artifact_bucket = artifact_bucket
        self._experiment_name = experiment_name
        self._cf_access_client_id = cf_access_client_id
        self._cf_access_client_secret = cf_access_client_secret
        if not self._uses_remote_tracking():
            try:
                import mlflow  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "mlflow dependency is required for MLflowTrackerAdapter. "
                    "Install with `uv sync --extra tracking`."
                ) from exc
            self._mlflow = mlflow
            self._mlflow.set_tracking_uri(tracking_uri)
            self._mlflow.set_experiment(experiment_name)

    def _uses_remote_tracking(self) -> bool:
        scheme = urlsplit(self._tracking_uri).scheme.lower()
        return scheme in {"http", "https"}

    def log_pipeline_run(
        self,
        run_name: str,
        params: dict[str, object],
        metrics: dict[str, float],
        artifacts: list[Path],
    ) -> str | None:
        if self._uses_remote_tracking():
            _ = artifacts
            return self._log_remote_run(
                run_name=run_name,
                params=params,
                metrics=metrics,
            )

        assert self._mlflow is not None
        with self._mlflow.start_run(run_name=run_name) as run:
            self._mlflow.log_params(params)
            self._mlflow.log_metrics(metrics)
            for artifact in artifacts:
                if artifact.exists():
                    self._log_artifact(artifact)
            return _run_id_from_active_run(run)

    def _log_artifact(self, artifact: Path) -> None:
        artifact_path = _mlflow_artifact_subdir(artifact)
        if artifact_path is None:
            self._mlflow.log_artifact(str(artifact))
            return
        try:
            self._mlflow.log_artifact(str(artifact), artifact_path=artifact_path)
        except TypeError:
            self._mlflow.log_artifact(str(artifact))

    def _log_remote_run(
        self,
        *,
        run_name: str,
        params: dict[str, object],
        metrics: dict[str, float],
    ) -> str | None:
        experiment_id = self._ensure_remote_experiment()
        run = self._mlflow_request(
            "POST",
            "/api/2.0/mlflow/runs/create",
            {
                "experiment_id": experiment_id,
                "tags": [
                    {"key": "mlflow.runName", "value": run_name},
                ],
            },
        )
        info = cast(dict[str, Any], run.get("run", {})).get("info", {})
        run_id = str(cast(dict[str, Any], info).get("run_id", "")).strip()
        if not run_id:
            raise RuntimeError("mlflow remote create_run response missing run_id")
        batch = {
            "run_id": run_id,
            "params": [
                {"key": str(key), "value": _string_value(value)}
                for key, value in params.items()
            ],
            "metrics": [
                {
                    "key": str(key),
                    "value": float(value),
                    "timestamp": _timestamp_millis(),
                    "step": 0,
                }
                for key, value in metrics.items()
            ],
            "tags": [],
        }
        if batch["params"] or batch["metrics"]:
            self._mlflow_request("POST", "/api/2.0/mlflow/runs/log-batch", batch)
        self._mlflow_request(
            "POST",
            "/api/2.0/mlflow/runs/update",
            {"run_id": run_id, "status": "FINISHED"},
        )
        return run_id

    def _ensure_remote_experiment(self) -> str:
        try:
            lookup = self._mlflow_request(
                "GET",
                (
                    "/api/2.0/mlflow/experiments/get-by-name?"
                    + urlencode({"experiment_name": self._experiment_name})
                ),
            )
        except RuntimeError as exc:
            if not _is_missing_experiment_error(exc):
                raise
            lookup = {}
        experiment = cast(dict[str, Any], lookup.get("experiment", {}))
        experiment_id = str(experiment.get("experiment_id", "")).strip()
        if experiment_id:
            return experiment_id
        created = self._mlflow_request(
            "POST",
            "/api/2.0/mlflow/experiments/create",
            {"name": self._experiment_name},
        )
        experiment_id = str(created.get("experiment_id", "")).strip()
        if not experiment_id:
            raise RuntimeError("mlflow remote create_experiment response missing id")
        return experiment_id

    def _mlflow_request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._tracking_uri.rstrip('/')}{path}"
        body = (
            json.dumps(payload, ensure_ascii=True).encode("utf-8")
            if payload is not None
            else None
        )
        req = request.Request(
            url,
            method=method,
            data=body,
            headers=self._mlflow_headers(),
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"mlflow remote request failed path={path} status={exc.code} detail={detail}"
            ) from exc
        decoded = json.loads(text) if text.strip() else {}
        if not isinstance(decoded, dict):
            raise RuntimeError(f"unexpected mlflow response type for path={path}")
        return cast(dict[str, Any], decoded)

    def _mlflow_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "discoverex-mlflow-tracker/1.0",
        }
        cf_id = self._cf_access_client_id.strip()
        cf_secret = self._cf_access_client_secret.strip()
        if cf_id and cf_secret:
            headers["CF-Access-Client-Id"] = cf_id
            headers["CF-Access-Client-Secret"] = cf_secret
        return headers


def _run_id_from_active_run(run: object) -> str | None:
    info = getattr(run, "info", None)
    run_id = getattr(info, "run_id", "")
    text = str(run_id).strip()
    return text or None


def _mlflow_artifact_subdir(artifact: Path) -> str | None:
    parts = artifact.parts
    if "scenes" not in parts:
        return None
    scenes_index = parts.index("scenes")
    if len(parts) <= scenes_index + 4:
        return None
    relative_parent = Path(*parts[scenes_index + 3 : -1])
    text = relative_parent.as_posix()
    return text or None

def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _timestamp_millis() -> int:
    return int(time.time() * 1000)


def _is_missing_experiment_error(exc: RuntimeError) -> bool:
    text = str(exc)
    return "status=404" in text and (
        "RESOURCE_DOES_NOT_EXIST" in text or "get-by-name" in text
    )
