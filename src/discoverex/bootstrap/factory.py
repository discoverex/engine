from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hydra.utils import instantiate

from discoverex.adapters.outbound.bundle_store import LocalJsonBundleStore
from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.config import ValidatorPipelineConfig
from discoverex.domain.services.verification import ScoringWeights
from discoverex.models.types import ModelHandle
from discoverex.settings import AppSettings

from .config_defaults import resolve_config
from .context import AppContext


def _build_env_defaults(settings: AppSettings) -> dict[str, str]:
    runtime_cfg = settings.pipeline.runtime
    artifacts_root = Path(runtime_cfg.artifacts_root)
    return {
        "artifacts_root": str(artifacts_root),
        "artifact_bucket": settings.storage.artifact_bucket,
        "s3_endpoint_url": settings.storage.s3_endpoint_url,
        "aws_access_key_id": settings.storage.aws_access_key_id,
        "aws_secret_access_key": settings.storage.aws_secret_access_key,
        "metadata_db_url": settings.storage.metadata_db_url,
        "tracking_uri": settings.tracking.uri,
        "cf_access_client_id": settings.worker_http.cf_access_client_id,
        "cf_access_client_secret": settings.worker_http.cf_access_client_secret,
    }


def build_context(
    settings: AppSettings | dict[str, Any] | None = None,
    *,
    execution_snapshot: dict[str, object] | None = None,
    execution_snapshot_path: Path | None = None,
) -> AppContext:
    settings = resolve_config(settings)
    cfg = settings.pipeline
    artifacts_root = Path(cfg.runtime.artifacts_root)
    env_defaults = _build_env_defaults(settings)

    background_generator_model = instantiate(
        cfg.models.background_generator.as_kwargs()
    )
    background_upscaler_model = instantiate(cfg.models.background_upscaler.as_kwargs())
    object_generator_model = instantiate(cfg.models.object_generator.as_kwargs())
    hidden_region_model = instantiate(cfg.models.hidden_region.as_kwargs())
    inpaint_model = instantiate(cfg.models.inpaint.as_kwargs())
    perception_model = instantiate(cfg.models.perception.as_kwargs())
    fx_model = instantiate(cfg.models.fx.as_kwargs())

    artifact_store = instantiate(
        cfg.adapters.artifact_store.as_kwargs(), **env_defaults
    )
    metadata_store = instantiate(
        cfg.adapters.metadata_store.as_kwargs(), **env_defaults
    )
    tracker = instantiate(cfg.adapters.tracker.as_kwargs(), **env_defaults)
    scene_io = instantiate(cfg.adapters.scene_io.as_kwargs(), **env_defaults)
    report_writer = instantiate(cfg.adapters.report_writer.as_kwargs(), **env_defaults)

    return AppContext(
        settings=settings,
        background_generator_model=background_generator_model,
        background_upscaler_model=background_upscaler_model,
        object_generator_model=object_generator_model,
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
        execution_snapshot=execution_snapshot,
        execution_snapshot_path=execution_snapshot_path,
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
        LocalJsonBundleStore(Path(cfg.bundle_store_dir))
        if cfg.bundle_store_dir
        else None
    )

    return ValidatorOrchestrator(
        physical_port=physical_port,
        logical_port=logical_port,
        visual_port=visual_port,
        physical_handle=physical_handle,
        logical_handle=logical_handle,
        visual_handle=visual_handle,
        difficulty_min=cfg.thresholds.difficulty_min,
        difficulty_max=cfg.thresholds.difficulty_max,
        hidden_obj_min=cfg.thresholds.hidden_obj_min,
        scoring_weights=scoring_weights,
        bundle_store=bundle_store,
    )


def build_animate_context(
    config: dict[str, Any],
) -> Any:
    """Build AnimateOrchestrator from Hydra-resolved config dict."""
    from discoverex.application.use_cases.animate.orchestrator import (
        AnimateOrchestrator,
    )
    from discoverex.config.animate_schema import AnimatePipelineConfig

    cfg = AnimatePipelineConfig.model_validate(config)

    mode_classifier = instantiate(cfg.models.mode_classifier.as_kwargs())
    vision_analyzer = instantiate(cfg.models.vision_analyzer.as_kwargs())
    animation_generator = instantiate(cfg.models.animation_generation.as_kwargs())
    ai_validator = instantiate(cfg.models.ai_validator.as_kwargs())
    post_motion = instantiate(cfg.models.post_motion_classifier.as_kwargs())

    # load() lifecycle — Gemini needs api_key, ComfyUI/Dummy accept None.
    api_key = os.environ.get("GEMINI_API_KEY", "")
    handle: ModelHandle | None = (
        ModelHandle(name="gemini", version="v0", runtime="api", extra={"api_key": api_key})
        if api_key
        else None
    )
    for adapter in (
        mode_classifier, vision_analyzer, animation_generator,
        ai_validator, post_motion,
    ):
        if hasattr(adapter, "load"):
            adapter.load(handle)

    _inst = lambda c: instantiate(c.as_kwargs())  # noqa: E731
    aa = cfg.animate_adapters

    return AnimateOrchestrator(
        mode_classifier=mode_classifier,
        vision_analyzer=vision_analyzer,
        animation_generator=animation_generator,
        numerical_validator=_inst(aa.numerical_validator),
        ai_validator=ai_validator,
        post_motion_classifier=post_motion,
        bg_remover=_inst(aa.bg_remover),
        mask_generator=_inst(aa.mask_generator),
        keyframe_generator=_inst(aa.keyframe_generator),
        format_converter=_inst(aa.format_converter),
        image_upscaler=_inst(aa.image_upscaler),
        max_retries=cfg.max_retries,
    )
