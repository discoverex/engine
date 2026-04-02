"""Unit tests for animate domain entities."""

from __future__ import annotations

from pathlib import Path

from discoverex.domain.animate import (
    AIValidationContext,
    AIValidationFix,
    AnimationGenerationParams,
    AnimationValidation,
    AnimationValidationThresholds,
    FacingDirection,
    ModeClassification,
    MotionTravelType,
    PostMotionResult,
    ProcessingMode,
    TravelDirection,
    VisionAnalysis,
)
from discoverex.domain.animate_keyframe import (
    AnimationResult,
    ConvertedAsset,
    KeyframeAnimation,
    KeyframeConfig,
    KFKeyframe,
    TransparentSequence,
)


class TestEnums:
    def test_processing_mode_values(self) -> None:
        assert ProcessingMode.KEYFRAME_ONLY.value == "keyframe_only"
        assert ProcessingMode.MOTION_NEEDED.value == "motion_needed"

    def test_facing_direction_values(self) -> None:
        assert len(FacingDirection) == 5

    def test_motion_travel_type_values(self) -> None:
        assert len(MotionTravelType) == 7

    def test_travel_direction_values(self) -> None:
        assert len(TravelDirection) == 5


class TestModeClassification:
    def test_defaults(self) -> None:
        mc = ModeClassification(
            processing_mode=ProcessingMode.KEYFRAME_ONLY,
            has_deformable=False,
        )
        assert mc.is_scene is False
        assert mc.facing_direction == FacingDirection.NONE
        assert mc.suggested_action == ""
        assert mc.reason == ""

    def test_json_roundtrip(self) -> None:
        mc = ModeClassification(
            processing_mode=ProcessingMode.MOTION_NEEDED,
            has_deformable=True,
            is_scene=True,
            subject_desc="a bird",
            reason="has wings",
        )
        data = mc.model_dump()
        restored = ModeClassification(**data)
        assert restored.processing_mode == ProcessingMode.MOTION_NEEDED
        assert restored.is_scene is True


class TestVisionAnalysis:
    def test_creation(self) -> None:
        va = VisionAnalysis(
            object_desc="bird", action_desc="flap",
            moving_parts="wings", fixed_parts="body",
            moving_zone=[0.1, 0.2, 0.9, 0.8],
            frame_rate=16, frame_count=32,
            min_motion=0.03, max_motion=0.15, max_diff=0.20,
            positive="鸟", negative="静止",
        )
        assert va.pingpong is True
        assert va.bg_type == "solid"
        assert va.bg_remove is True
        assert len(va.moving_zone) == 4


class TestAnimationGenerationParams:
    def test_defaults(self) -> None:
        p = AnimationGenerationParams(
            positive="p", negative="n",
            frame_rate=16, frame_count=32, seed=42,
            output_dir="/tmp", stem="test", attempt=1,
        )
        assert p.pingpong is False
        assert p.mask_name is None


class TestValidationEntities:
    def test_thresholds_defaults(self) -> None:
        t = AnimationValidationThresholds()
        assert t.min_motion == 0.003
        assert t.max_edge_ratio == 0.08

    def test_validation_defaults(self) -> None:
        v = AnimationValidation(passed=True)
        assert v.failed_checks == []
        assert v.scores == {}

    def test_ai_context(self) -> None:
        ctx = AIValidationContext(
            current_fps=16, current_scale=0.65,
            positive="p", negative="n",
        )
        assert ctx.current_fps == 16

    def test_ai_fix_defaults(self) -> None:
        fix = AIValidationFix(passed=False, issues=["ghosting"])
        assert fix.frame_rate is None
        assert fix.scale is None


class TestPostMotionResult:
    def test_defaults(self) -> None:
        r = PostMotionResult(needs_keyframe=False)
        assert r.travel_type == MotionTravelType.NO_TRAVEL
        assert r.travel_direction == TravelDirection.NONE
        assert r.confidence == 0.0


class TestKeyframeEntities:
    def test_keyframe_config(self) -> None:
        c = KeyframeConfig(suggested_action="wobble")
        assert c.facing_direction == "none"
        assert c.loop is True

    def test_kf_keyframe_defaults(self) -> None:
        kf = KFKeyframe(t=0.5)
        assert kf.translateX == 0.0
        assert kf.scaleX == 1.0
        assert kf.glow_color is None

    def test_keyframe_animation(self) -> None:
        anim = KeyframeAnimation(
            animation_type="wobble",
            keyframes=[KFKeyframe(t=0.0), KFKeyframe(t=1.0)],
            duration_ms=1000, easing="ease-in-out",
        )
        assert anim.transform_origin == "center center"
        assert anim.loop is True
        assert len(anim.keyframes) == 2


class TestResultEntities:
    def test_animation_result(self) -> None:
        r = AnimationResult(video_path=Path("/tmp/v.mp4"), seed=42, attempt=1)
        assert r.video_path.suffix == ".mp4"

    def test_transparent_sequence_defaults(self) -> None:
        ts = TransparentSequence()
        assert ts.frames == []

    def test_converted_asset_defaults(self) -> None:
        ca = ConvertedAsset()
        assert ca.lottie_path is None
        assert ca.apng_path is None
        assert ca.webm_path is None
