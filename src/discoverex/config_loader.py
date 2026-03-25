from __future__ import annotations

from pathlib import Path

from discoverex.config import PipelineConfig, ValidatorPipelineConfig


def load_pipeline_config(
    config_name: str,
    config_dir: str | Path = "conf",
    overrides: list[str] | None = None,
) -> PipelineConfig:
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf

    cfg_dir = Path(config_dir).resolve()
    with initialize_config_dir(config_dir=str(cfg_dir), version_base=None):
        cfg = compose(config_name=config_name, overrides=overrides or [])
    data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(data, dict):
        raise ValueError("Hydra config must resolve to dict")
    return PipelineConfig.model_validate(data)


def coerce_pipeline_config(config: object) -> PipelineConfig:
    if not isinstance(config, dict):
        raise ValueError("resolved_config must be a dict")
    return PipelineConfig.model_validate(config)


def resolve_pipeline_config(
    *,
    config_name: str,
    config_dir: str | Path = "conf",
    overrides: list[str] | None = None,
    resolved_config: object | None = None,
) -> PipelineConfig:
    if resolved_config is not None:
        return coerce_pipeline_config(resolved_config)
    return load_pipeline_config(
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
    )


def load_raw_animate_config(
    config_name: str,
    config_dir: str | Path = "conf",
    overrides: list[str] | None = None,
) -> dict:
    """Load raw Hydra config dict for animate pipeline (no Pydantic validation)."""
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf

    cfg_dir = Path(config_dir).resolve()
    with initialize_config_dir(config_dir=str(cfg_dir), version_base=None):
        cfg = compose(config_name=config_name, overrides=overrides or [])
    data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(data, dict):
        raise ValueError("Hydra config must resolve to dict")
    return data


def load_validator_config(
    config_name: str = "validator",
    config_dir: str | Path = "conf",
    overrides: list[str] | None = None,
) -> ValidatorPipelineConfig:
    from hydra import compose, initialize_config_dir
    from omegaconf import OmegaConf

    cfg_dir = Path(config_dir).resolve()
    with initialize_config_dir(config_dir=str(cfg_dir), version_base=None):
        cfg = compose(config_name=config_name, overrides=overrides or [])
    data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(data, dict):
        raise ValueError("Hydra config must resolve to dict")
    return ValidatorPipelineConfig.model_validate(data)
