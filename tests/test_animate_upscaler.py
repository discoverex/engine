"""Tests for image upscaler — PilImageUpscaler and preprocessing integration."""

from __future__ import annotations

import struct
import tempfile
import zlib
from pathlib import Path

from discoverex.adapters.outbound.animate.dummy_animate import DummyImageUpscaler
from discoverex.adapters.outbound.animate.pil_upscaler import PilImageUpscaler
from discoverex.application.use_cases.animate.preprocessing import (
    UPSCALE_THRESHOLD,
    _compute_scale_factor,
    preprocess_image_simple,
)


def _make_png(w: int, h: int, path: Path) -> Path:
    """Create a minimal valid PNG with given dimensions."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    scanlines = b""
    for _ in range(h):
        scanlines += b"\x00" + b"\xff\x80\x40" * w
    raw = zlib.compress(scanlines)
    path.write_bytes(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    return path


class TestComputeScaleFactor:
    def test_small_image(self) -> None:
        factor = _compute_scale_factor(60, 83, 480)
        assert 3.0 < factor < 4.0

    def test_medium_image(self) -> None:
        factor = _compute_scale_factor(150, 200, 480)
        assert 1.0 < factor < 2.0

    def test_max_clamp(self) -> None:
        factor = _compute_scale_factor(5, 5, 480)
        assert factor == 8.0


class TestPilImageUpscaler:
    def test_lanczos_upscale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = _make_png(50, 50, Path(tmpdir) / "small.png")
            upscaler = PilImageUpscaler()
            result = upscaler.upscale(img, 4.0, "illustration")
            assert result.exists()
            from PIL import Image
            out = Image.open(result)
            assert out.size == (200, 200)

    def test_nearest_for_pixel_art(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = _make_png(32, 32, Path(tmpdir) / "pixel.png")
            upscaler = PilImageUpscaler()
            result = upscaler.upscale(img, 4.0, "pixel_art")
            assert result.exists()
            from PIL import Image
            out = Image.open(result)
            assert out.size == (128, 128)

    def test_output_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = _make_png(20, 20, Path(tmpdir) / "sprite.png")
            upscaler = PilImageUpscaler()
            result = upscaler.upscale(img, 2.0)
            assert result.name == "sprite_upscaled.png"


class TestDummyImageUpscaler:
    def test_returns_input(self) -> None:
        dummy = DummyImageUpscaler()
        p = Path("/tmp/test.png")
        assert dummy.upscale(p, 4.0) == p


class TestPreprocessWithUpscaler:
    def test_small_image_is_upscaled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = _make_png(60, 83, Path(tmpdir) / "tiny.png")
            out = Path(tmpdir) / "processed.png"
            upscaler = PilImageUpscaler()
            preprocess_image_simple(img, out, upscaler=upscaler, art_style="illustration")
            assert out.exists()
            from PIL import Image
            result = Image.open(out)
            assert result.size == (480, 480)

    def test_large_image_skips_upscale(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = _make_png(300, 400, Path(tmpdir) / "large.png")
            out = Path(tmpdir) / "processed.png"
            upscaler = PilImageUpscaler()
            preprocess_image_simple(img, out, upscaler=upscaler)
            assert out.exists()

    def test_no_upscaler_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = _make_png(60, 83, Path(tmpdir) / "tiny.png")
            out = Path(tmpdir) / "processed.png"
            preprocess_image_simple(img, out)
            assert out.exists()

    def test_threshold_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            img = _make_png(UPSCALE_THRESHOLD, UPSCALE_THRESHOLD, Path(tmpdir) / "boundary.png")
            out = Path(tmpdir) / "processed.png"
            upscaler = PilImageUpscaler()
            preprocess_image_simple(img, out, upscaler=upscaler)
            assert out.exists()
