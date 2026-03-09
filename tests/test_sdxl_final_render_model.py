from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.adapters.outbound.models.sdxl_final_render import SdxlFinalRenderModel
from discoverex.models.types import FxRequest


class _FakeImage:
    def save(self, path: Path) -> None:
        path.write_bytes(b"rendered-image")


def test_sdxl_final_render_uses_input_image(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    model = SdxlFinalRenderModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_final_render.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("fx-v1")
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), color="white").save(source)

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return _FakeImage()

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)
    output_path = tmp_path / "final.png"
    pred = model.predict(
        handle,
        FxRequest(
            image_ref=str(source),
            mode="final_render",
            params={"output_path": str(output_path), "prompt": "playable scene"},
        ),
    )

    assert pred["output_path"] == str(output_path)
    assert output_path.exists()
    assert captured["prompt"] == "playable scene"
