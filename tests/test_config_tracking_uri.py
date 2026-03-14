from __future__ import annotations

from discoverex.config_loader import load_pipeline_config


def test_mlflow_local_tracker_uses_runtime_env_tracking_uri() -> None:
    cfg = load_pipeline_config(config_name="gen_verify", config_dir="conf")
    assert (
        cfg.adapters.tracker.as_kwargs()["tracking_uri"] == cfg.runtime.env.tracking_uri
    )
