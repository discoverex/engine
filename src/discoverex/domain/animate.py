"""Animate pipeline domain entities — classification, analysis, and validation."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enum definitions
# ---------------------------------------------------------------------------


class ProcessingMode(str, Enum):
    KEYFRAME_ONLY = "keyframe_only"
    MOTION_NEEDED = "motion_needed"


class FacingDirection(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    NONE = "none"


class MotionTravelType(str, Enum):
    NO_TRAVEL = "no_travel"
    TRAVEL_LATERAL = "travel_lateral"
    TRAVEL_VERTICAL = "travel_vertical"
    TRAVEL_DIAGONAL = "travel_diagonal"
    AMPLIFY_HOP = "amplify_hop"
    AMPLIFY_SWAY = "amplify_sway"
    AMPLIFY_FLOAT = "amplify_float"


class TravelDirection(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    NONE = "none"


class ArtStyle(str, Enum):
    ILLUSTRATION = "illustration"
    PHOTO = "photo"
    PIXEL_ART = "pixel_art"
    VECTOR = "vector"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Classification / analysis entities
# ---------------------------------------------------------------------------


class ModeClassification(BaseModel):
    processing_mode: ProcessingMode
    has_deformable: bool
    is_scene: bool = False
    subject_desc: str = ""
    facing_direction: FacingDirection = FacingDirection.NONE
    suggested_action: str = ""
    reason: str = ""
    art_style: ArtStyle = ArtStyle.UNKNOWN


class VisionAnalysis(BaseModel):
    object_desc: str
    action_desc: str
    moving_parts: str
    fixed_parts: str
    moving_zone: list[float]  # [x1, y1, x2, y2] relative coords
    frame_rate: int
    frame_count: int
    min_motion: float
    max_motion: float
    max_diff: float
    positive: str  # WAN Chinese prompt
    negative: str
    pingpong: bool = True
    bg_type: str = "solid"
    bg_remove: bool = True
    reason: str = ""


class AnimationGenerationParams(BaseModel):
    """Parameter bundle for ComfyUI workflow execution."""

    positive: str
    negative: str
    frame_rate: int
    frame_count: int
    seed: int
    output_dir: str
    stem: str
    attempt: int
    pingpong: bool = False
    mask_name: str | None = None


# ---------------------------------------------------------------------------
# Validation entities
# ---------------------------------------------------------------------------


class AnimationValidationThresholds(BaseModel):
    """Numerical validation thresholds — injected via Hydra config."""

    min_motion: float = 0.003
    max_motion: float = 0.15
    max_repeat_peaks: int = 12
    max_edge_ratio: float = 0.08
    max_return_diff: float = 0.40
    max_center_drift: float = 0.12


class AnimationValidation(BaseModel):
    passed: bool
    failed_checks: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)


class AIValidationContext(BaseModel):
    """Current generation state passed to AIValidationPort.validate()."""

    current_fps: int
    current_scale: float
    positive: str
    negative: str


class AIValidationFix(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    reason: str = ""
    frame_rate: int | None = None
    scale: float | None = None
    positive: str | None = None
    negative: str | None = None


# ---------------------------------------------------------------------------
# Post-motion classification
# ---------------------------------------------------------------------------


class PostMotionResult(BaseModel):
    needs_keyframe: bool
    travel_type: MotionTravelType = MotionTravelType.NO_TRAVEL
    travel_direction: TravelDirection = TravelDirection.NONE
    confidence: float = 0.0
    suggested_keyframe: str = ""
    reason: str = ""
