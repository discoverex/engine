from __future__ import annotations

import pytest

from discoverex.adapters.outbound.models.hf_hidden_region import HFHiddenRegionModel
from discoverex.adapters.outbound.models.hf_inpaint import HFInpaintModel
from discoverex.models.types import HiddenRegionRequest, InpaintRequest, ModelHandle


def test_hf_hidden_region_prefers_transformers_path_when_available() -> None:
    model = HFHiddenRegionModel(model_id="facebook/detr-resnet-50")
    handle = ModelHandle(
        name="hidden_region_model",
        version="v1",
        runtime="hf",
        extra={"runtime_available": True},
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        model,
        "_predict_with_transformers_if_available",
        lambda _handle, _request: [(1.0, 2.0, 3.0, 4.0)],
    )
    boxes = model.predict(handle, HiddenRegionRequest(width=320, height=240))
    monkeypatch.undo()
    assert boxes == [(1.0, 2.0, 3.0, 4.0)]


def test_hf_hidden_region_falls_back_when_realpath_missing() -> None:
    model = HFHiddenRegionModel(model_id="facebook/detr-resnet-50")
    handle = ModelHandle(
        name="hidden_region_model",
        version="v1",
        runtime="hf",
        extra={"runtime_available": False},
    )
    boxes = model.predict(handle, HiddenRegionRequest(width=320, height=240))
    assert len(boxes) == 3


def test_hf_inpaint_prefers_transformers_path_when_available() -> None:
    model = HFInpaintModel(model_id="stabilityai/stable-diffusion-2-inpainting")
    handle = ModelHandle(
        name="inpaint_model",
        version="v1",
        runtime="hf",
        extra={"runtime_available": True},
    )
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(model, "_predict_quality", lambda _handle, _request: 0.91)
    pred = model.predict(
        handle,
        InpaintRequest(region_id="r1", bbox=(1.0, 2.0, 3.0, 4.0)),
    )
    monkeypatch.undo()
    assert pred["quality_score"] == 0.91


def test_hf_inpaint_falls_back_when_realpath_missing() -> None:
    model = HFInpaintModel(model_id="stabilityai/stable-diffusion-2-inpainting")
    handle = ModelHandle(
        name="inpaint_model",
        version="v1",
        runtime="hf",
        extra={"runtime_available": False},
    )
    pred = model.predict(handle, InpaintRequest(region_id="r1", prompt="make hidden"))
    assert pred["quality_score"] == 0.86
