from __future__ import annotations

from pathlib import Path
from typing import Any

from hydra.utils import instantiate

from discoverex.adapters.outbound.bundle_store import LocalJsonBundleStore
from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.config import PipelineConfig, ValidatorPipelineConfig
from discoverex.domain.services.verification import ScoringWeights
from discoverex.models.types import ModelHandle

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


def _make_handle(name: str, cfg_dict: dict[str, Any]) -> ModelHandle:
    return ModelHandle(
        name=name,
        version="v0",
        runtime="hf",
        model_id=str(cfg_dict.get("model_id", "")),
        device=str(cfg_dict.get("device", "cuda")),
        dtype=str(cfg_dict.get("dtype", "float16")),
    )


def _build_scoring_weights(cfg: ValidatorPipelineConfig) -> ScoringWeights:
    """weights_path 가 지정되면 JSON 파일에서 로드, 아니면 cfg.weights 에서 빌드."""
    if cfg.weights_path is not None:
        weights_file = Path(cfg.weights_path)
        return ScoringWeights.model_validate_json(
            weights_file.read_text(encoding="utf-8")
        )
    return ScoringWeights(**cfg.weights.model_dump())


def build_validator_context(
    config: ValidatorPipelineConfig | dict[str, Any] | None = None,
) -> ValidatorOrchestrator:
    cfg: ValidatorPipelineConfig
    if isinstance(config, ValidatorPipelineConfig):
        cfg = config
    elif isinstance(config, dict):
        cfg = ValidatorPipelineConfig.model_validate(config)
    else:
        raise ValueError("config must be a ValidatorPipelineConfig or dict")

    physical_port = instantiate(cfg.models.physical_extraction.as_kwargs())
    logical_port = instantiate(cfg.models.logical_extraction.as_kwargs())
    visual_port = instantiate(cfg.models.visual_verification.as_kwargs())

    physical_handle = _make_handle(
        "physical_extraction", cfg.models.physical_extraction.model_dump()
    )
    logical_handle = _make_handle(
        "logical_extraction", cfg.models.logical_extraction.model_dump()
    )
    visual_handle = _make_handle(
        "visual_verification", cfg.models.visual_verification.model_dump()
    )

    scoring_weights = _build_scoring_weights(cfg)
    bundle_store = (
        LocalJsonBundleStore(Path(cfg.bundle_store_dir)) if cfg.bundle_store_dir else None
    )

    return ValidatorOrchestrator(
        physical_port=physical_port,
        logical_port=logical_port,
        visual_port=visual_port,
        physical_handle=physical_handle,
        logical_handle=logical_handle,
        visual_handle=visual_handle,
        pass_threshold=cfg.thresholds.pass_threshold,
        scoring_weights=scoring_weights,
        bundle_store=bundle_store,
    )
