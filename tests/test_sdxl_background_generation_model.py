from __future__ import annotations

from pathlib import Path

import pytest

from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.adapters.outbound.models.sdxl_background_generation import (
    SdxlBackgroundGenerationModel,
)
from discoverex.models.types import FxRequest


class _FakeImage:
    def save(self, path: Path) -> None:
        path.write_bytes(b"fake-image")


def test_sdxl_background_generation_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    model = SdxlBackgroundGenerationModel(strict_runtime=False, refiner_model_id=None)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_background_generation.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("bg-v1")

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return _FakeImage()

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)

    output_path = tmp_path / "background.png"
    pred = model.predict(
        handle,
        FxRequest(
            mode="background",
            params={
                "output_path": str(output_path),
                "prompt": "aurora over ice canyon",
                "width": 512,
                "height": 384,
            },
        ),
    )

    assert pred["output_path"] == str(output_path)
    assert output_path.exists()
    assert captured["prompt"] == "aurora over ice canyon"
