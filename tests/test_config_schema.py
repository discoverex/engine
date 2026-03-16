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
    assert cfg.models.object_generator.target
    assert cfg.model_versions.background_generator == "background-generator-v0"
    assert cfg.model_versions.object_generator == "object-generator-v0"


def test_generator_sdxl_gpu_profile_loads_dedicated_generator_stack() -> None:
    cfg = load_pipeline_config(
        config_name="gen_verify",
        config_dir="conf",
        overrides=["profile=generator_sdxl_gpu"],
    )
    assert cfg.models.background_generator.target.endswith(
        "SdxlBackgroundGenerationModel"
    )
    assert cfg.models.object_generator.target.endswith(
        "SdxlBackgroundGenerationModel"
    )
    assert cfg.models.inpaint.target.endswith("SdxlInpaintModel")
    assert cfg.models.fx.target.endswith("CopyImageFxModel")
    assert cfg.runtime.width == 512
    assert cfg.runtime.height == 512
    assert cfg.runtime.model_runtime.offload_mode == "model"
    assert cfg.runtime.model_runtime.enable_fp8_layerwise_casting is False


def test_pipeline_config_rejects_invalid_threshold() -> None:
    cfg = load_pipeline_config(config_name="gen_verify", config_dir="conf")
    data = cfg.model_dump(mode="python", by_alias=True)
    data["thresholds"]["logical_pass"] = 1.5
    with pytest.raises(ValueError):
        PipelineConfig.model_validate(data)


def test_generator_sdxl_gpu_v2_8gb_profile_loads_v2_stack() -> None:
    cfg = load_pipeline_config(
        config_name="gen_verify",
        config_dir="conf",
        overrides=["profile=generator_sdxl_gpu_v2_8gb"],
    )
    assert cfg.flows is not None
    assert cfg.flows.generate.target.endswith("generate_v2_compat")
    assert cfg.models.inpaint.model_dump(mode="python")["inpaint_mode"] == (
        "similarity_overlay_v2"
    )
    assert cfg.models.object_generator.target.endswith(
        "LayerDiffuseObjectGenerationModel"
    )
    assert cfg.models.inpaint.model_dump(mode="python")["overlay_alpha"] == 0.5
    assert cfg.models.inpaint.model_dump(mode="python")["final_inpaint_strength"] == 0.22
    assert cfg.models.inpaint.model_dump(mode="python")["final_inpaint_steps"] == 8
    assert cfg.models.object_generator.model_dump(mode="python")[
        "default_num_inference_steps"
    ] == 30
    assert cfg.models.object_generator.model_dump(mode="python")[
        "default_guidance_scale"
    ] == 5.0
    assert cfg.models.object_generator.model_dump(mode="python")["offload_mode"] == "model"
    assert cfg.models.inpaint.model_dump(mode="python")["final_context_size"] == 512
    assert cfg.runtime.width == 256
    assert cfg.runtime.height == 256
    assert cfg.runtime.background_upscale_factor == 4
    assert cfg.runtime.model_runtime.offload_mode == "sequential"
