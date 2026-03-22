from __future__ import annotations

from pathlib import Path

from PIL import Image

from discoverex.adapters.outbound.models.sam_object_mask import SamObjectMaskExtractor


def test_sam_extractor_runs_mask_prediction_even_when_alpha_exists(tmp_path: Path) -> None:
    source = tmp_path / "transparent-object.png"
    image = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            image.putpixel((x, y), (10, 20, 30, 255))
    image.save(source)

    extractor = SamObjectMaskExtractor()
    predicted = Image.new("L", (32, 32), color=0)
    for x in range(10, 22):
        for y in range(10, 22):
            predicted.putpixel((x, y), 255)
    extractor._predict_mask = lambda image: predicted  # type: ignore[method-assign]

    extracted = extractor.extract(
        image_path=source,
        output_prefix=tmp_path / "masked",
    )

    mask = Image.open(extracted["mask"]).convert("L")
    assert mask.getbbox() == (8, 8, 24, 24)
    assert extracted["mask_source"] == "raw_alpha_preserved"
    assert extracted["alpha_has_signal"] is True
    assert extracted["alpha_bbox"] == "8,8,24,24"
    assert float(extracted["alpha_nonzero_ratio"]) > 0.0


def test_sam_extractor_preserves_raw_alpha_when_predicted_mask_is_too_small(
    tmp_path: Path,
) -> None:
    source = tmp_path / "transparent-object.png"
    image = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            image.putpixel((x, y), (40, 80, 120, 255))
    image.save(source)

    extractor = SamObjectMaskExtractor()
    predicted = Image.new("L", (32, 32), color=0)
    for x in range(14, 18):
        for y in range(14, 18):
            predicted.putpixel((x, y), 255)
    extractor._predict_mask = lambda image: predicted  # type: ignore[method-assign]

    extracted = extractor.extract(
        image_path=source,
        output_prefix=tmp_path / "masked",
    )

    mask = Image.open(extracted["mask"]).convert("L")
    assert mask.getbbox() == (8, 8, 24, 24)
    assert extracted["mask_source"] == "raw_alpha_preserved"
