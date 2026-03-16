from __future__ import annotations

from pathlib import Path

from PIL import Image

from discoverex.adapters.outbound.models.sam_object_mask import SamObjectMaskExtractor


def test_sam_extractor_prefers_existing_alpha_mask(tmp_path: Path) -> None:
    source = tmp_path / "transparent-object.png"
    image = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
    for x in range(8, 24):
        for y in range(8, 24):
            image.putpixel((x, y), (10, 20, 30, 255))
    image.save(source)

    extracted = SamObjectMaskExtractor().extract(
        image_path=source,
        output_prefix=tmp_path / "masked",
    )

    mask = Image.open(extracted["mask"]).convert("L")
    assert mask.getbbox() == (8, 8, 24, 24)
