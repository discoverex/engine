from __future__ import annotations

from types import SimpleNamespace

from discoverex.bootstrap.factory import _build_env_defaults


def test_build_env_defaults_does_not_override_tracker_experiment_name() -> None:
    settings = SimpleNamespace(
        pipeline=SimpleNamespace(runtime=SimpleNamespace(artifacts_root="artifacts")),
        storage=SimpleNamespace(
            artifact_bucket="bucket",
            s3_endpoint_url="",
            aws_access_key_id="",
            aws_secret_access_key="",
            metadata_db_url="sqlite:///meta.db",
        ),
        tracking=SimpleNamespace(uri="https://mlflow.example"),
        worker_http=SimpleNamespace(
            cf_access_client_id="cf-id",
            cf_access_client_secret="cf-secret",
        ),
    )

    defaults = _build_env_defaults(settings)

    assert "experiment_name" not in defaults
