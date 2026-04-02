"""Animate pipeline port interfaces.

All ports follow the engine's Protocol-first design.
Model/API ports use the load(handle) → task() → unload() lifecycle
consistent with the validator pipeline pattern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from discoverex.domain.animate import (
    AIValidationContext,
    AIValidationFix,
    AnimationGenerationParams,
    AnimationValidation,
    AnimationValidationThresholds,
    ModeClassification,
    PostMotionResult,
    VisionAnalysis,
)
from discoverex.domain.animate_keyframe import (
    AnimationResult,
    ConvertedAsset,
    KeyframeAnimation,
    KeyframeConfig,
    TransparentSequence,
)
from discoverex.models.types import ModelHandle

# ---------------------------------------------------------------------------
# Gemini Vision ports — load/task/unload lifecycle
# ---------------------------------------------------------------------------


class ModeClassificationPort(Protocol):
    """Stage 1: Determine KEYFRAME_ONLY vs MOTION_NEEDED."""

    def load(self, handle: ModelHandle) -> None: ...

    def classify(self, image: Path) -> ModeClassification: ...

    def unload(self) -> None: ...


class VisionAnalysisPort(Protocol):
    """Gemini Vision analysis for motion parameter determination."""

    def load(self, handle: ModelHandle) -> None: ...

    def analyze(self, image: Path) -> VisionAnalysis: ...

    def analyze_with_exclusion(
        self, image: Path, exclude_action: str
    ) -> VisionAnalysis: ...

    def unload(self) -> None: ...


class AIValidationPort(Protocol):
    """Gemini Vision subjective quality assessment with parameter fixes."""

    def load(self, handle: ModelHandle) -> None: ...

    def validate(
        self,
        video: Path,
        original_image: Path,
        context: AIValidationContext,
    ) -> AIValidationFix: ...

    def unload(self) -> None: ...


class PostMotionClassificationPort(Protocol):
    """Stage 2: Determine keyframe travel type after WAN generation."""

    def load(self, handle: ModelHandle) -> None: ...

    def classify(self, video: Path, original_image: Path) -> PostMotionResult: ...

    def unload(self) -> None: ...


# ---------------------------------------------------------------------------
# ComfyUI port — load/generate/unload lifecycle
# ---------------------------------------------------------------------------


class AnimationGenerationPort(Protocol):
    """WAN I2V generation via ComfyUI HTTP API."""

    def load(self, handle: ModelHandle) -> None: ...

    def generate(
        self,
        handle: ModelHandle,
        uploaded_image: str,
        params: AnimationGenerationParams,
    ) -> AnimationResult: ...

    def unload(self) -> None: ...


# ---------------------------------------------------------------------------
# Numerical validation port (no load/unload — CPU-only)
# ---------------------------------------------------------------------------


class AnimationValidationPort(Protocol):
    """Numerical quality validation (8 metrics)."""

    def validate(
        self,
        video: Path,
        original_analysis: VisionAnalysis,
        thresholds: AnimationValidationThresholds,
    ) -> AnimationValidation: ...


# ---------------------------------------------------------------------------
# Processing ports (no load/unload — lightweight utilities)
# ---------------------------------------------------------------------------


class BackgroundRemovalPort(Protocol):
    """Remove background from video frames → transparent PNG sequence."""

    def remove(self, video: Path, fps: int = 16) -> TransparentSequence: ...


class KeyframeGenerationPort(Protocol):
    """Generate CSS keyframe animations."""

    def generate(self, config: KeyframeConfig) -> KeyframeAnimation: ...


class FormatConversionPort(Protocol):
    """Convert transparent PNG sequence to APNG/WebM/Lottie."""

    def convert(
        self, frames: list[Path], preset: str = "original", fps: int = 16
    ) -> ConvertedAsset: ...


class MaskGenerationPort(Protocol):
    """Generate binary mask for moving zone."""

    def generate(
        self, image_path: Path, moving_zone: list[float], output_dir: Path | None = None
    ) -> Path: ...


class ImageUpscalerPort(Protocol):
    """Upscale small images before WAN canvas placement."""

    def upscale(self, image: Path, scale_factor: float, art_style: str = "illustration") -> Path: ...
