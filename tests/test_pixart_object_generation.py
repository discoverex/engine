from __future__ import annotations

from pathlib import Path

from PIL import Image

from discoverex.adapters.outbound.models.pixart_object_generation import (
    PixArtObjectGenerationModel,
)
from discoverex.models.types import FxRequest


def test_pixart_object_generation_writes_debug_sidecars(tmp_path: Path, monkeypatch) -> None:
    model = PixArtObjectGenerationModel()
    monkeypatch.setattr(
        model,
        "_generate_base_image",
        lambda **_kwargs: Image.new("RGB", (32, 32), color=(12, 34, 56)),
    )
    handle = type("_Handle", (), {"device": "cuda"})()
    output_path = tmp_path / "object.png"
    preview_path = tmp_path / "object.preview.png"
    alpha_path = tmp_path / "object.alpha.png"
    visualization_path = tmp_path / "object.visualization.png"

    prediction = model.predict(
        handle,
        FxRequest(
            mode="object_generation",
            params={
                "output_path": str(output_path),
                "preview_output_path": str(preview_path),
                "alpha_output_path": str(alpha_path),
                "visualization_output_path": str(visualization_path),
                "prompt": "butterfly",
                "width": 32,
                "height": 32,
            },
        ),
    )

    assert prediction["output_path"] == str(output_path)
    assert output_path.exists()
    assert preview_path.exists()
    assert alpha_path.exists()
    assert visualization_path.exists()
    assert Image.open(output_path).mode == "RGBA"
