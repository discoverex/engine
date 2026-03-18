"""Integration test — animate_pipeline flow function with Dummy adapters."""

from __future__ import annotations

import struct
import tempfile
import zlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

from discoverex.config.schema import FlowsConfig, HydraComponentConfig, PipelineConfig
from discoverex.flows.subflows import animate_pipeline


def _minimal_png() -> bytes:
    """Generate a minimal valid 1x1 white PNG."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return (
            struct.pack(">I", len(data))
            + c
            + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = zlib.compress(b"\x00\xff\xff\xff")
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def _dummy_config() -> PipelineConfig:
    """Build a minimal PipelineConfig for testing."""
    dummy_models = {
        "background_generator": {"_target_": "dummy"},
        "hidden_region": {"_target_": "dummy"},
        "inpaint": {"_target_": "dummy"},
        "perception": {"_target_": "dummy"},
        "fx": {"_target_": "dummy"},
    }
    dummy_adapters = {
        "artifact_store": {"_target_": "dummy"},
        "metadata_store": {"_target_": "dummy"},
        "tracker": {"_target_": "dummy"},
        "scene_io": {"_target_": "dummy"},
        "report_writer": {"_target_": "dummy"},
    }
    flows = {
        "generate": {"_target_": "dummy"},
        "verify": {"_target_": "dummy"},
        "animate": {
            "_target_": "discoverex.flows.subflows.animate_pipeline",
        },
    }
    return PipelineConfig(
        models=dummy_models,  # type: ignore[arg-type]
        adapters=dummy_adapters,  # type: ignore[arg-type]
        flows=FlowsConfig(**{k: HydraComponentConfig(**v) for k, v in flows.items()}),
    )


def _mock_build_animate_context(config: Any) -> Any:
    """Build a real orchestrator with all Dummy adapters."""
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
    from discoverex.application.use_cases.animate.orchestrator import (
        AnimateOrchestrator,
    )
    from discoverex.models.types import ModelHandle

    handle = ModelHandle(name="test", version="v0", runtime="dummy")
    mc = DummyModeClassifier()
    mc.load(handle)
    va = DummyVisionAnalyzer()
    va.load(handle)
    ag = DummyAnimationGenerator()
    ag.load(handle)
    ai = DummyAIValidator()
    ai.load(handle)
    pm = DummyPostMotionClassifier()
    pm.load(handle)

    return AnimateOrchestrator(
        mode_classifier=mc,
        vision_analyzer=va,
        animation_generator=ag,
        numerical_validator=DummyAnimationValidator(),
        ai_validator=ai,
        post_motion_classifier=pm,
        bg_remover=DummyBgRemover(),
        mask_generator=DummyMaskGenerator(),
        keyframe_generator=DummyKeyframeGenerator(),
        format_converter=DummyFormatConverter(),
        max_retries=2,
    )


class TestAnimatePipelineFlow:
    def test_missing_image_path(self) -> None:
        config = _dummy_config()
        result = animate_pipeline(args={}, config=config)
        assert result["status"] == "failed"
        assert "image_path" in result["failure_reason"]

    @patch(
        "discoverex.bootstrap.factory.build_animate_context",
        side_effect=_mock_build_animate_context,
    )
    def test_full_flow_with_dummies(self, mock_build: Any) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = Path(tmpdir) / "test.png"
            img.write_bytes(_minimal_png())

            config = _dummy_config()
            result = animate_pipeline(
                args={"image_path": str(img)},
                config=config,
            )

            assert result["status"] == "success"
            assert result["mode"] == "motion_needed"
            assert result["attempts"] >= 1
