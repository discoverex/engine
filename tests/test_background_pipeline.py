from __future__ import annotations

from pathlib import Path

from PIL import Image

from discoverex.application.use_cases.gen_verify.background_pipeline import (
    _upscale_background_image,
)


def test_upscale_background_image_doubles_resolution(tmp_path: Path) -> None:
    source = tmp_path / "background.png"
    output = tmp_path / "background.upscaled.png"
    Image.new("RGB", (64, 48), color=(120, 140, 160)).save(source)

    result = _upscale_background_image(
        image_path=source,
        output_path=output,
        factor=2,
    )

    assert result["path"] == output
    assert result["width"] == 128
    assert result["height"] == 96
    assert Image.open(output).size == (128, 96)
