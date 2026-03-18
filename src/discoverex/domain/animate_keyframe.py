"""Animate pipeline domain entities — keyframe structures and generation results."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Keyframe structures
# ---------------------------------------------------------------------------


class KeyframeConfig(BaseModel):
    """Request parameter for KeyframeGenerationPort.generate()."""

    suggested_action: str
    facing_direction: str = "none"
    duration_ms: int | None = None
    loop: bool = True


class KFKeyframe(BaseModel):
    """Single keyframe — CSS transform property set."""

    t: float
    translateX: float = 0.0
    translateY: float = 0.0
    rotate: float = 0.0
    scaleX: float = 1.0
    scaleY: float = 1.0
    opacity: float = 1.0
    glow_color: str | None = None
    glow_radius: float | None = None


class KeyframeAnimation(BaseModel):
    animation_type: str
    keyframes: list[KFKeyframe]
    duration_ms: int
    easing: str
    transform_origin: str = "center center"
    loop: bool = True
    suggested_action: str = ""
    facing_direction: str = ""


# ---------------------------------------------------------------------------
# Generation results
# ---------------------------------------------------------------------------


class AnimationResult(BaseModel):
    video_path: Path
    seed: int
    attempt: int


class TransparentSequence(BaseModel):
    frames: list[Path] = Field(default_factory=list)


class ConvertedAsset(BaseModel):
    lottie_path: Path | None = None
    apng_path: Path | None = None
    webm_path: Path | None = None
