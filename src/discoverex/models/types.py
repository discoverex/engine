from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict


@dataclass(slots=True)
class ModelRuntimeContext:
    device: str = "cuda"
    dtype: str = "float16"
    batch_size: int = 1
    precision: str = "fp16"
    seed: int | None = None


@dataclass(slots=True)
class ModelHandle:
    name: str
    version: str
    runtime: str
    model_id: str = ""
    revision: str = "main"
    tokenizer_id: str | None = None
    device: str = "cuda"
    dtype: str = "float16"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HiddenRegionRequest:
    image_ref: str | Path | None = None
    image_bytes: bytes | None = None
    width: int = 0
    height: int = 0
    thresholds: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class InpaintRequest:
    image_ref: str | Path | None = None
    region_id: str = ""
    bbox: tuple[float, float, float, float] | None = None
    region_mask_ref: str | Path | None = None
    prompt: str = ""
    negative_prompt: str = ""


@dataclass(slots=True)
class PerceptionRequest:
    image_ref: str | Path | None = None
    region_count: int = 0
    regions: list[dict[str, Any]] = field(default_factory=list)
    question_context: str = ""


@dataclass(slots=True)
class FxRequest:
    image_ref: str | Path | None = None
    mode: str = "default"
    params: dict[str, Any] = field(default_factory=dict)


class FxPrediction(TypedDict, total=False):
    fx: str
    output_path: str
    image_ref: str
    composite_image_ref: str
    artifact_path: str
