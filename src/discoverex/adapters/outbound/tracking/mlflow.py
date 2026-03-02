from __future__ import annotations

from pathlib import Path
from typing import Any


class MLflowTrackerAdapter:
    def __init__(
        self,
        experiment_name: str = "discoverex-core",
        tracking_uri: str = "sqlite:///mlflow.db",
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
        self._mlflow.set_tracking_uri(tracking_uri)
        self._mlflow.set_experiment(experiment_name)

    def log_pipeline_run(
        self,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, float],
        artifacts: list[Path],
    ) -> None:
        with self._mlflow.start_run(run_name=run_name):
            self._mlflow.log_params(params)
            self._mlflow.log_metrics(metrics)
            for artifact in artifacts:
                if artifact.exists():
                    self._mlflow.log_artifact(str(artifact))
