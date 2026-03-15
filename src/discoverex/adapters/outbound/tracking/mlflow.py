from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit


class MLflowTrackerAdapter:
    def __init__(
        self,
        experiment_name: str = "discoverex-core",
        tracking_uri: str = "sqlite:///mlflow.db",
        artifact_bucket: str = "discoverex-artifacts",
        **_: str,
    ) -> None:
        try:
            import mlflow  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "mlflow dependency is required for MLflowTrackerAdapter. "
                "Install with `uv sync --extra tracking`."
            ) from exc
        self._mlflow = mlflow
        self._tracking_uri = tracking_uri
        self._artifact_bucket = artifact_bucket
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
        with self._mlflow.start_run(run_name=run_name) as run:
            self._mlflow.log_params(params)
            self._mlflow.log_metrics(metrics)
            if self._uses_remote_tracking():
                return _run_id_from_active_run(run)
            for artifact in artifacts:
                if artifact.exists():
                    self._mlflow.log_artifact(str(artifact))
            return _run_id_from_active_run(run)


def _run_id_from_active_run(run: object) -> str | None:
    info = getattr(run, "info", None)
    run_id = getattr(info, "run_id", "")
    text = str(run_id).strip()
    return text or None
