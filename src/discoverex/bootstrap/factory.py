from __future__ import annotations

from pathlib import Path
from typing import Any

from hydra.utils import instantiate

from discoverex.config import PipelineConfig

from .config_defaults import resolve_config
from .context import AppContext


def _build_env_defaults(config: PipelineConfig) -> dict[str, str]:
    runtime_cfg = config.runtime
    runtime_env = runtime_cfg.env
    artifacts_root = Path(runtime_cfg.artifacts_root)
    return {
        "artifacts_root": str(artifacts_root),
        "artifact_bucket": runtime_env.artifact_bucket,
        "s3_endpoint_url": runtime_env.s3_endpoint_url,
        "aws_access_key_id": runtime_env.aws_access_key_id,
        "aws_secret_access_key": runtime_env.aws_secret_access_key,
        "metadata_db_url": runtime_env.metadata_db_url,
        "tracking_uri": runtime_env.tracking_uri,
        "experiment_name": "discoverex-core",
    }


def build_context(config: PipelineConfig | dict[str, Any] | None = None) -> AppContext:
    cfg = resolve_config(config)
    artifacts_root = Path(cfg.runtime.artifacts_root)
    env_defaults = _build_env_defaults(cfg)

    hidden_region_model = instantiate(cfg.models.hidden_region.as_kwargs())
    inpaint_model = instantiate(cfg.models.inpaint.as_kwargs())
    perception_model = instantiate(cfg.models.perception.as_kwargs())
    fx_model = instantiate(cfg.models.fx.as_kwargs())

    artifact_store = instantiate(cfg.adapters.artifact_store.as_kwargs(), **env_defaults)
    metadata_store = instantiate(cfg.adapters.metadata_store.as_kwargs(), **env_defaults)
    tracker = instantiate(cfg.adapters.tracker.as_kwargs(), **env_defaults)
    scene_io = instantiate(cfg.adapters.scene_io.as_kwargs(), **env_defaults)
    report_writer = instantiate(cfg.adapters.report_writer.as_kwargs(), **env_defaults)

    return AppContext(
        hidden_region_model=hidden_region_model,
        inpaint_model=inpaint_model,
        perception_model=perception_model,
        fx_model=fx_model,
        artifact_store=artifact_store,
        metadata_store=metadata_store,
        tracker=tracker,
        scene_io=scene_io,
        report_writer=report_writer,
        artifacts_root=artifacts_root,
        runtime=cfg.runtime,
        thresholds=cfg.thresholds,
        model_versions=cfg.model_versions,
    )
