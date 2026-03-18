"""Port contract tests — verify all Dummy adapters satisfy port Protocols."""

from __future__ import annotations

import tempfile
from pathlib import Path

from discoverex.adapters.outbound.animate.dummy_animate import (
    DummyAnimationValidator,
    DummyBgRemover,
    DummyFormatConverter,
    DummyKeyframeGenerator,
    DummyMaskGenerator,
)
from discoverex.adapters.outbound.models.dummy_animate import (
    DummyAIValidator,
    DummyAnimationGenerator,
    DummyModeClassifier,
    DummyPostMotionClassifier,
    DummyVisionAnalyzer,
)
from discoverex.domain.animate import (
    AIValidationContext,
    AIValidationFix,
    AnimationGenerationParams,
    AnimationValidation,
    AnimationValidationThresholds,
    ModeClassification,
    PostMotionResult,
    ProcessingMode,
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

_HANDLE = ModelHandle(name="test", version="v0", runtime="dummy")
_IMAGE = Path("/dev/null")


class TestModeClassifierContract:
    def test_load_classify_unload(self) -> None:
        adapter = DummyModeClassifier()
        adapter.load(_HANDLE)
        result = adapter.classify(_IMAGE)
        adapter.unload()
        assert isinstance(result, ModeClassification)
        assert result.processing_mode == ProcessingMode.MOTION_NEEDED


class TestVisionAnalyzerContract:
    def test_analyze(self) -> None:
        adapter = DummyVisionAnalyzer()
        adapter.load(_HANDLE)
        result = adapter.analyze(_IMAGE)
        adapter.unload()
        assert isinstance(result, VisionAnalysis)
        assert len(result.moving_zone) == 4
        assert result.frame_rate > 0

    def test_analyze_with_exclusion(self) -> None:
        adapter = DummyVisionAnalyzer()
        adapter.load(_HANDLE)
        result = adapter.analyze_with_exclusion(_IMAGE, "wing flap")
        adapter.unload()
        assert isinstance(result, VisionAnalysis)
        assert result.action_desc == "alternate action"


class TestAIValidatorContract:
    def test_validate(self) -> None:
        adapter = DummyAIValidator()
        adapter.load(_HANDLE)
        ctx = AIValidationContext(
            current_fps=16, current_scale=0.65,
            positive="p", negative="n",
        )
        result = adapter.validate(_IMAGE, _IMAGE, ctx)
        adapter.unload()
        assert isinstance(result, AIValidationFix)
        assert result.passed is True


class TestPostMotionClassifierContract:
    def test_classify(self) -> None:
        adapter = DummyPostMotionClassifier()
        adapter.load(_HANDLE)
        result = adapter.classify(_IMAGE, _IMAGE)
        adapter.unload()
        assert isinstance(result, PostMotionResult)
        assert result.needs_keyframe is False


class TestAnimationGeneratorContract:
    def test_generate(self) -> None:
        adapter = DummyAnimationGenerator()
        adapter.load(_HANDLE)
        with tempfile.TemporaryDirectory() as tmpdir:
            params = AnimationGenerationParams(
                positive="p", negative="n",
                frame_rate=16, frame_count=32, seed=42,
                output_dir=tmpdir, stem="test", attempt=1,
            )
            result = adapter.generate(_HANDLE, "test.png", params)
            assert isinstance(result, AnimationResult)
            assert result.seed == 42
            assert result.video_path.exists()
        adapter.unload()


class TestAnimationValidatorContract:
    def test_validate(self) -> None:
        adapter = DummyAnimationValidator()
        analysis = VisionAnalysis(
            object_desc="bird", action_desc="flap",
            moving_parts="wings", fixed_parts="body",
            moving_zone=[0.1, 0.2, 0.9, 0.8],
            frame_rate=16, frame_count=32,
            min_motion=0.03, max_motion=0.15, max_diff=0.20,
            positive="鸟", negative="静止",
        )
        thresholds = AnimationValidationThresholds()
        result = adapter.validate(_IMAGE, analysis, thresholds)
        assert isinstance(result, AnimationValidation)
        assert result.passed is True


class TestBgRemoverContract:
    def test_remove(self) -> None:
        adapter = DummyBgRemover()
        result = adapter.remove(_IMAGE)
        assert isinstance(result, TransparentSequence)
        assert len(result.frames) == 4


class TestKeyframeGeneratorContract:
    def test_generate(self) -> None:
        adapter = DummyKeyframeGenerator()
        config = KeyframeConfig(suggested_action="wobble")
        result = adapter.generate(config)
        assert isinstance(result, KeyframeAnimation)
        assert result.animation_type == "wobble"
        assert len(result.keyframes) == 3


class TestFormatConverterContract:
    def test_convert(self) -> None:
        adapter = DummyFormatConverter()
        result = adapter.convert([], preset="web")
        assert isinstance(result, ConvertedAsset)


class TestMaskGeneratorContract:
    def test_generate(self) -> None:
        adapter = DummyMaskGenerator()
        result = adapter.generate(_IMAGE, [0.1, 0.2, 0.9, 0.8])
        assert isinstance(result, Path)
        assert result.exists()
