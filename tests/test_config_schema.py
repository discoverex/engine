from __future__ import annotations

import pytest

from discoverex.config import PipelineConfig
from discoverex.config_loader import load_pipeline_config


def test_hydra_config_loads_into_pipeline_config() -> None:
    cfg = load_pipeline_config(config_name="gen_verify", config_dir="conf")
    assert isinstance(cfg, PipelineConfig)
    assert cfg.runtime.width == 1024
    assert cfg.runtime.model_runtime.device in {"cpu", "cuda"}
    assert cfg.models.background_generator.target
    assert cfg.model_versions.background_generator == "background-generator-v0"


def test_generator_sdxl_gpu_profile_loads_dedicated_generator_stack() -> None:
    cfg = load_pipeline_config(
        config_name="gen_verify",
        config_dir="conf",
        overrides=["profile=generator_sdxl_gpu"],
    )
    assert cfg.models.background_generator.target.endswith(
        "SdxlBackgroundGenerationModel"
    )
    assert cfg.models.inpaint.target.endswith("SdxlInpaintModel")
    assert cfg.models.fx.target.endswith("SdxlFinalRenderModel")


def test_pipeline_config_rejects_invalid_threshold() -> None:
    cfg = load_pipeline_config(config_name="gen_verify", config_dir="conf")
    data = cfg.model_dump(mode="python", by_alias=True)
    data["thresholds"]["logical_pass"] = 1.5
    with pytest.raises(ValueError):
        PipelineConfig.model_validate(data)
