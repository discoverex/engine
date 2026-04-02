"""Integration test — AnimateOrchestrator with all Dummy adapters."""

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
from discoverex.application.use_cases.animate.orchestrator import (
    AnimateOrchestrator,
    AnimateResult,
)
from discoverex.domain.animate import ProcessingMode
from discoverex.models.types import ModelHandle


def _build_orchestrator(output_dir: Path) -> AnimateOrchestrator:
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
        output_dir=output_dir,
        max_retries=3,
    )


class TestAnimateOrchestratorMotionNeeded:
    def test_full_pipeline_with_dummies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "output"
            orch = _build_orchestrator(out)

            # Create a dummy input image
            img = Path(tmpdir) / "test_input.png"
            # Minimal valid PNG (1x1 white pixel)
            import struct
            import zlib

            def _minimal_png() -> bytes:
                sig = b"\x89PNG\r\n\x1a\n"

                def chunk(ctype: bytes, data: bytes) -> bytes:
                    c = ctype + data
                    return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

                ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
                raw = zlib.compress(b"\x00\xff\xff\xff")
                return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")

            img.write_bytes(_minimal_png())

            result = orch.run(img)

            assert isinstance(result, AnimateResult)
            assert result.success is True
            assert result.mode is not None
            assert result.mode.processing_mode == ProcessingMode.MOTION_NEEDED
            assert result.attempts >= 1
