from __future__ import annotations

from pathlib import Path

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from discoverex.config import PipelineConfig


def load_pipeline_config(
    config_name: str,
    config_dir: str | Path = "conf",
    overrides: list[str] | None = None,
) -> PipelineConfig:
    cfg_dir = Path(config_dir).resolve()
    with initialize_config_dir(config_dir=str(cfg_dir), version_base=None):
        cfg = compose(config_name=config_name, overrides=overrides or [])
    data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(data, dict):
        raise ValueError("Hydra config must resolve to dict")
    return PipelineConfig.model_validate(data)
