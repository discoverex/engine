from __future__ import annotations

from pathlib import Path

import pytest

from discoverex.adapters.outbound.models.fx_tiny_sd import TinySDFxModel
from discoverex.models.types import FxRequest


class _FakeImage:
    def save(self, path: Path) -> None:
        path.write_bytes(b"fake-image")


def test_tiny_sd_fx_predict_writes_output_and_passes_dimensions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    model = TinySDFxModel(strict_runtime=False)
    handle = model.load("fx-v1")

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return _FakeImage()

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)

    output_path = tmp_path / "composite.png"
    pred = model.predict(
        handle,
        FxRequest(
            mode="default",
            params={
                "output_path": str(output_path),
                "width": 320,
                "height": 240,
                "seed": 42,
            },
        ),
    )

    assert pred["output_path"] == str(output_path)
    assert output_path.exists()
    assert captured["width"] == 320
    assert captured["height"] == 240
    assert captured["num_inference_steps"] == model.default_num_inference_steps


def test_tiny_sd_fx_predict_requires_output_path() -> None:
    model = TinySDFxModel(strict_runtime=False)
    handle = model.load("fx-v1")

    with pytest.raises(ValueError, match="output_path"):
        model.predict(handle, FxRequest(mode="default", params={}))
