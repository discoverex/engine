from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from pydantic import BaseModel, Field


class ModelRuntimeContext(BaseModel):
    device: str = "cuda"
    dtype: str = "float16"
    batch_size: int = 1
    precision: str = "fp16"
    seed: int | None = None


class ModelHandle(BaseModel):
    name: str
    version: str
    runtime: str
    model_id: str = ""
    revision: str = "main"
    tokenizer_id: str | None = None
    device: str = "cuda"
    dtype: str = "float16"
    extra: dict[str, Any] = Field(default_factory=dict)


class HiddenRegionRequest(BaseModel):
    image_ref: str | Path | None = None
    image_bytes: bytes | None = None
    width: int = 0
    height: int = 0
    thresholds: dict[str, float] = Field(default_factory=dict)


class InpaintRequest(BaseModel):
    image_ref: str | Path | None = None
    region_id: str = ""
    bbox: tuple[float, float, float, float] | None = None
    region_mask_ref: str | Path | None = None
    prompt: str = ""
    negative_prompt: str = ""


class PerceptionRequest(BaseModel):
    image_ref: str | Path | None = None
    region_count: int = 0
    regions: list[dict[str, Any]] = Field(default_factory=list)
    question_context: str = ""


class FxRequest(BaseModel):
    image_ref: str | Path | None = None
    mode: str = "default"
    params: dict[str, Any] = Field(default_factory=dict)


class FxPrediction(TypedDict, total=False):
    fx: str
    output_path: str
    image_ref: str
    composite_image_ref: str
    artifact_path: str
