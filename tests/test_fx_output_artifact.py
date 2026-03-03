from __future__ import annotations

from pathlib import Path

from discoverex.adapters.outbound.models.dummy import DummyFxModel
from discoverex.models.types import FxRequest


def test_dummy_fx_model_writes_output_image(tmp_path: Path) -> None:
    model = DummyFxModel()
    handle = model.load("fx-v0")
    output_path = tmp_path / "composite.png"

    pred = model.predict(
        handle,
        FxRequest(
            image_ref="bg://dummy",
            mode="default",
            params={"output_path": str(output_path)},
        ),
    )

    assert pred["output_path"] == str(output_path)
    assert output_path.exists()
    assert output_path.stat().st_size > 0
