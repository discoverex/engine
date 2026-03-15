from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.adapters.outbound.models.sdxl_inpaint import SdxlInpaintModel
from discoverex.models.types import InpaintRequest


def test_sdxl_inpaint_writes_patch_and_composited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = SdxlInpaintModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("inpaint-v1")
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), color="white").save(source)

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        image = kwargs["image"]
        mask = kwargs["mask"]
        assert image.size == (128, 64)
        assert mask.size == (128, 64)
        generated = image.copy()
        ImageDraw.Draw(generated).ellipse((40, 14, 88, 50), fill=(20, 40, 220))
        return generated

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)
    output_path = tmp_path / "out.png"
    pred = model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r1",
            bbox=(10, 10, 20, 10),
            output_path=str(output_path),
            generation_prompt="hidden ruby",
        ),
    )

    assert pred["composited_image_ref"] == str(output_path)
    assert Path(pred["object_image_ref"]).exists()
    assert Path(pred["object_mask_ref"]).exists()
    assert output_path.exists()
    patch_path = Path(str(output_path).replace(".png", ".patch.png"))
    object_path = Path(str(output_path).replace(".png", ".object.png"))
    mask_path = Path(str(output_path).replace(".png", ".mask.png"))
    assert patch_path.exists()
    assert object_path.exists()
    assert mask_path.exists()
    assert Image.open(output_path).size == (64, 64)
    assert Image.open(patch_path).size == (128, 64)
    assert Image.open(object_path).size == (128, 64)
    assert Image.open(mask_path).size == (128, 64)
    composited = Image.open(output_path)
    assert composited.getpixel((5, 5)) == (255, 255, 255)
    assert composited.getpixel((20, 15)) != (255, 255, 255)


def test_sdxl_inpaint_normalizes_large_output_and_keeps_mask_local(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = SdxlInpaintModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("inpaint-v1")
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), color=(240, 240, 240)).save(source)

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        image = kwargs["image"]
        generated = Image.new("RGB", (1024, 1024), color=(242, 242, 242))
        ImageDraw.Draw(generated).ellipse((420, 360, 620, 640), fill=(10, 20, 180))
        assert image.size == (128, 64)
        return generated

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)
    output_path = tmp_path / "out-large.png"
    pred = model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r2",
            bbox=(8, 12, 24, 12),
            output_path=str(output_path),
            generation_prompt="hidden blue gem",
        ),
    )

    mask = Image.open(pred["object_mask_ref"])
    assert mask.size == (128, 64)
    bbox = mask.getbbox()
    assert bbox is not None
    assert bbox[0] > 8
    assert bbox[1] > 4
    assert bbox[2] < 120
    assert bbox[3] < 60


def test_resize_patch_to_long_side_uses_multiple_of_8() -> None:
    from discoverex.adapters.outbound.models.sdxl_inpaint_inference import (
        resize_patch_to_long_side,
    )

    patch = Image.new("RGB", (82, 77), color="white")
    resized, size = resize_patch_to_long_side(patch, 128)

    assert resized.size == size
    assert size == (128, 120)
