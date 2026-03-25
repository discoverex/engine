"""Dummy implementations for animate processing ports.

Deterministic responses for testing without ffmpeg/scipy dependencies.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from discoverex.domain.animate import (
    AnimationValidation,
    AnimationValidationThresholds,
    VisionAnalysis,
)
from discoverex.domain.animate_keyframe import (
    ConvertedAsset,
    KeyframeAnimation,
    KeyframeConfig,
    KFKeyframe,
    TransparentSequence,
)


class DummyAnimationValidator:
    """AnimationValidationPort dummy."""

    def validate(
        self,
        video: Path,
        original_analysis: VisionAnalysis,
        thresholds: AnimationValidationThresholds,
    ) -> AnimationValidation:
        return AnimationValidation(
            passed=True,
            scores={"motion": 0.05, "raw_motion": 0.04},
        )


class DummyBgRemover:
    """BackgroundRemovalPort dummy."""

    def remove(self, video: Path, fps: int = 16) -> TransparentSequence:
        tmp = Path(tempfile.mkdtemp())
        frames = []
        for i in range(4):
            p = tmp / f"dummy_frame_{i:04d}.png"
            p.write_bytes(b"dummy_png")
            frames.append(p)
        return TransparentSequence(frames=frames)


class DummyKeyframeGenerator:
    """KeyframeGenerationPort dummy."""

    def generate(self, config: KeyframeConfig) -> KeyframeAnimation:
        return KeyframeAnimation(
            animation_type="wobble",
            keyframes=[
                KFKeyframe(t=0.0, rotate=0.0),
                KFKeyframe(t=0.5, rotate=5.0),
                KFKeyframe(t=1.0, rotate=0.0),
            ],
            duration_ms=1500,
            easing="ease-in-out",
            suggested_action=config.suggested_action,
            facing_direction=config.facing_direction,
        )


class DummyFormatConverter:
    """FormatConversionPort dummy."""

    def convert(
        self, frames: list[Path], preset: str = "original", fps: int = 16,
    ) -> ConvertedAsset:
        return ConvertedAsset()


class DummyMaskGenerator:
    """MaskGenerationPort dummy."""

    def generate(
        self, image_path: Path, moving_zone: list[float],
        output_dir: Path | None = None,
    ) -> Path:
        out = Path(tempfile.mkdtemp()) / "dummy_mask.png"
        out.write_bytes(b"dummy_mask")
        return out


class DummyImageUpscaler:
    """ImageUpscalerPort dummy — returns input unchanged."""

    def upscale(
        self, image: Path, scale_factor: float, art_style: str = "illustration",
    ) -> Path:
        return image
