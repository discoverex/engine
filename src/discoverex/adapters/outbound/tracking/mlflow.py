from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class _CloudflareAccessRequestHeaderProvider:
    def in_context(self) -> bool:
        return bool(
            os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
            and os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
        )

    def request_headers(self) -> dict[str, str]:
        return {
            "CF-Access-Client-Id": os.getenv("CF_ACCESS_CLIENT_ID", "").strip(),
            "CF-Access-Client-Secret": os.getenv(
                "CF_ACCESS_CLIENT_SECRET", ""
            ).strip(),
        }


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
        self._register_request_headers()
        self._mlflow.set_tracking_uri(tracking_uri)
        self._mlflow.set_experiment(experiment_name)

    def _register_request_headers(self) -> None:
        if not self._uses_remote_tracking():
            return
        try:
            from mlflow.tracking.request_header import registry
        except Exception:
            return
        if any(
            isinstance(provider, _CloudflareAccessRequestHeaderProvider)
            for provider in registry._request_header_provider_registry
        ):
            return
        registry._request_header_provider_registry.register(
            _CloudflareAccessRequestHeaderProvider
        )

    def _uses_remote_tracking(self) -> bool:
        scheme = urlsplit(self._tracking_uri).scheme.lower()
        return scheme in {"http", "https"}

    def _artifact_tags(
        self, params: dict[str, Any], artifacts: list[Path]
    ) -> dict[str, str]:
        scene_id = str(params.get("scene_id", "")).strip()
        version_id = str(params.get("version_id", "")).strip()
        if not scene_id or not version_id:
            return {}
        key_base = f"s3://{self._artifact_bucket}/scenes/{scene_id}/{version_id}"
        tags: dict[str, str] = {}
        for artifact in artifacts:
            if artifact.name == "scene.json":
                tags["artifact_scene_json_uri"] = f"{key_base}/scene.json"
            elif artifact.name == "verification.json":
                tags["artifact_verification_uri"] = f"{key_base}/verification.json"
            elif artifact.name == "prompt_bundle.json":
                tags["artifact_prompt_bundle_uri"] = f"{key_base}/prompt_bundle.json"
        return tags

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
            if self._uses_remote_tracking():
                tags = self._artifact_tags(params, artifacts)
                for key, value in tags.items():
                    self._mlflow.set_tag(key, value)
                self._mlflow.set_tag("artifact_logging_mode", "metadata_only")
                return
            for artifact in artifacts:
                if artifact.exists():
                    self._mlflow.log_artifact(str(artifact))
