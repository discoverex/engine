from __future__ import annotations

from pathlib import Path

from PIL import Image

from discoverex.adapters.outbound.models.layerdiffuse_object_generation import (
    LayerDiffuseObjectGenerationModel,
)
from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.models.types import FxRequest


def test_layerdiffuse_object_generator_writes_rgba_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    model = LayerDiffuseObjectGenerationModel(strict_runtime=True)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.layerdiffuse_object_generation.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat",
                (),
                {"__version__": "4.46.0", "MT5Tokenizer": object()},
            )(),
            reason="",
        ),
    )
    monkeypatch.setattr(
        model,
        "_generate_rgba",
        lambda **_kwargs: Image.new("RGBA", (512, 512), color=(10, 20, 30, 200)),
    )
    handle = model.load("layerdiffuse-v1")
    output_path = tmp_path / "object.png"
    prediction = model.predict(
        handle,
        FxRequest(
            mode="object_generation",
            params={
                "output_path": str(output_path),
                "width": 512,
                "height": 512,
                "prompt": "hidden key",
            },
        ),
    )

    assert prediction["output_path"] == str(output_path)
    assert output_path.exists()
    assert Image.open(output_path).mode == "RGBA"
