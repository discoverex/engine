from __future__ import annotations

from discoverex.adapters.outbound.models.dummy import DummyFxModel
from discoverex.models.types import FxRequest


def test_dummy_fx_prediction_exposes_output_path_when_requested() -> None:
    adapter = DummyFxModel()
    handle = adapter.load("fx-v1")
    prediction = adapter.predict(
        handle,
        FxRequest(mode="default", params={"output_path": "/tmp/composite.png"}),
    )
    assert prediction["fx"] == "default"
    assert prediction["output_path"] == "/tmp/composite.png"
