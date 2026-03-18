"""Dummy implementations for all animate model ports.

Deterministic responses for testing without GPU/API dependencies.
"""

from __future__ import annotations

from pathlib import Path

from discoverex.domain.animate import (
    AIValidationContext,
    AIValidationFix,
    AnimationGenerationParams,
    FacingDirection,
    ModeClassification,
    MotionTravelType,
    PostMotionResult,
    ProcessingMode,
    TravelDirection,
    VisionAnalysis,
)
from discoverex.domain.animate_keyframe import AnimationResult
from discoverex.models.types import ModelHandle


class DummyModeClassifier:
    """ModeClassificationPort dummy."""

    def load(self, handle: ModelHandle) -> None:
        pass

    def classify(self, image: Path) -> ModeClassification:
        return ModeClassification(
            processing_mode=ProcessingMode.MOTION_NEEDED,
            has_deformable=True,
            subject_desc="test_sprite",
            facing_direction=FacingDirection.RIGHT,
            suggested_action="",
            reason="dummy classification",
        )

    def unload(self) -> None:
        pass


class DummyVisionAnalyzer:
    """VisionAnalysisPort dummy."""

    def load(self, handle: ModelHandle) -> None:
        pass

    def analyze(self, image: Path) -> VisionAnalysis:
        return VisionAnalysis(
            object_desc="test bird",
            action_desc="wing flap",
            moving_parts="left wing, right wing",
            fixed_parts="body, legs",
            moving_zone=[0.2, 0.1, 0.8, 0.7],
            frame_rate=16,
            frame_count=32,
            min_motion=0.03,
            max_motion=0.15,
            max_diff=0.20,
            positive="鸟扇动翅膀",
            negative="静止",
            reason="dummy analysis",
        )

    def analyze_with_exclusion(
        self, image: Path, exclude_action: str,
    ) -> VisionAnalysis:
        result = self.analyze(image)
        return result.model_copy(update={"action_desc": "alternate action"})

    def unload(self) -> None:
        pass


class DummyAIValidator:
    """AIValidationPort dummy."""

    def load(self, handle: ModelHandle) -> None:
        pass

    def validate(
        self, video: Path, original_image: Path, context: AIValidationContext,
    ) -> AIValidationFix:
        return AIValidationFix(passed=True, reason="dummy pass")

    def unload(self) -> None:
        pass


class DummyPostMotionClassifier:
    """PostMotionClassificationPort dummy."""

    def load(self, handle: ModelHandle) -> None:
        pass

    def classify(self, video: Path, original_image: Path) -> PostMotionResult:
        return PostMotionResult(
            needs_keyframe=False,
            travel_type=MotionTravelType.NO_TRAVEL,
            travel_direction=TravelDirection.NONE,
            confidence=0.9,
            reason="dummy no travel",
        )

    def unload(self) -> None:
        pass


class DummyAnimationGenerator:
    """AnimationGenerationPort dummy."""

    def load(self, handle: ModelHandle) -> None:
        pass

    def generate(
        self,
        handle: ModelHandle,
        uploaded_image: str,
        params: AnimationGenerationParams,
    ) -> AnimationResult:
        dummy_path = Path(params.output_dir) / f"{params.stem}_dummy.mp4"
        dummy_path.parent.mkdir(parents=True, exist_ok=True)
        dummy_path.write_bytes(b"dummy_video_content")
        return AnimationResult(
            video_path=dummy_path, seed=params.seed, attempt=params.attempt,
        )

    def unload(self) -> None:
        pass
