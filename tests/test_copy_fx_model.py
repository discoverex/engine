from __future__ import annotations

from pathlib import Path

from PIL import Image

from discoverex.adapters.outbound.models.copy_fx import CopyImageFxModel
from discoverex.models.types import FxRequest


def test_copy_fx_copies_source_image_to_output(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "out" / "final.png"
    Image.new("RGB", (32, 24), color="red").save(source)

    model = CopyImageFxModel()
    handle = model.load("v1")
    prediction = model.predict(
        handle,
        FxRequest(image_ref=str(source), params={"output_path": str(output)}),
    )

    assert prediction["output_path"] == str(output)
    assert output.exists()
    assert output.read_bytes() == source.read_bytes()
