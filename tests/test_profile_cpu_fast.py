from __future__ import annotations

from discoverex.config_loader import load_pipeline_config


def test_cpu_fast_profile_overrides_models_and_runtime() -> None:
    cfg = load_pipeline_config(
        config_name="gen_verify",
        overrides=["profile=cpu_fast"],
    )
    assert cfg.runtime.model_runtime.device == "cpu"
    assert cfg.runtime.width == 320
    assert cfg.runtime.height == 240
    assert cfg.models.hidden_region.target.endswith("HFHiddenRegionModel")
    assert cfg.models.inpaint.target.endswith("HFInpaintModel")
    assert cfg.models.perception.target.endswith("HFPerceptionModel")
    assert cfg.models.fx.target.endswith("TinySDFxModel")
    assert (
        cfg.models.hidden_region.model_dump(mode="python")["model_id"]
        == "hustvl/yolos-tiny"
    )
