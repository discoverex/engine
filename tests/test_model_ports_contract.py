from __future__ import annotations

import pytest

import discoverex.adapters.outbound.models.hf_perception as hf_perception_module
from discoverex.adapters.outbound.models.dummy import (
    DummyFxModel,
    DummyHiddenRegionModel,
    DummyInpaintModel,
    DummyPerceptionModel,
)
from discoverex.adapters.outbound.models.hf_perception import HFPerceptionModel
from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.adapters.outbound.models.tiny_torch_hidden_region import (
    TinyTorchHiddenRegionModel,
)
from discoverex.adapters.outbound.models.tiny_torch_inpaint import TinyTorchInpaintModel
from discoverex.adapters.outbound.models.tiny_torch_perception import (
    TinyTorchPerceptionModel,
)
from discoverex.models.types import (
    FxRequest,
    HiddenRegionRequest,
    InpaintRequest,
    PerceptionRequest,
)


def test_dummy_models_accept_request_objects() -> None:
    hidden = DummyHiddenRegionModel()
    hidden_handle = hidden.load("hidden-v1")
    boxes = hidden.predict(hidden_handle, HiddenRegionRequest(width=100, height=200))
    assert len(boxes) == 3

    inpaint = DummyInpaintModel()
    inpaint_handle = inpaint.load("inpaint-v1")
    details = inpaint.predict(inpaint_handle, InpaintRequest(region_id="r-1"))
    assert details["region_id"] == "r-1"

    perception = DummyPerceptionModel()
    perception_handle = perception.load("perception-v1")
    pred = perception.predict(perception_handle, PerceptionRequest(region_count=3))
    assert 0.0 <= pred["confidence"] <= 1.0

    fx = DummyFxModel()
    fx_handle = fx.load("fx-v1")
    fx_pred = fx.predict(fx_handle, FxRequest(mode="default"))
    assert fx_pred["fx"] == "default"


def test_hf_adapter_loads_without_runtime_when_not_strict() -> None:
    adapter = HFPerceptionModel(
        model_id="openai/clip-vit-base-patch32", strict_runtime=False
    )
    handle = adapter.load("perception-v2")
    assert handle.runtime == "hf"
    assert handle.model_id == "openai/clip-vit-base-patch32"


def test_hf_adapter_records_fallback_metadata_when_runtime_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hf_perception_module,
        "resolve_runtime",
        lambda: RuntimeResolution(available=False, reason="runtime unavailable"),
    )
    monkeypatch.setattr(
        hf_perception_module,
        "resolve_device",
        lambda preferred_device, _torch: preferred_device,
    )
    adapter = HFPerceptionModel(
        model_id="openai/clip-vit-base-patch32", strict_runtime=False
    )
    handle = adapter.load("perception-v2")
    assert handle.extra["fallback_used"] is True
    assert handle.extra["runtime_available"] is False
    assert handle.extra["fallback_reason"] == "runtime unavailable"


def test_hf_adapter_strict_mode_raises_when_runtime_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hf_perception_module,
        "resolve_runtime",
        lambda: RuntimeResolution(available=False, reason="runtime unavailable"),
    )
    adapter = HFPerceptionModel(
        model_id="openai/clip-vit-base-patch32", strict_runtime=True
    )
    with pytest.raises(RuntimeError, match="runtime unavailable"):
        adapter.load("perception-v2")


def test_tiny_torch_models_accept_request_objects() -> None:
    pytest.importorskip("torch")

    hidden = TinyTorchHiddenRegionModel(device="cpu", strict_runtime=True)
    hidden_handle = hidden.load("hidden-v1")
    boxes = hidden.predict(hidden_handle, HiddenRegionRequest(width=64, height=64))
    assert len(boxes) >= 2

    inpaint = TinyTorchInpaintModel(device="cpu", strict_runtime=True)
    inpaint_handle = inpaint.load("inpaint-v1")
    details = inpaint.predict(
        inpaint_handle,
        InpaintRequest(region_id="r-1", bbox=(1.0, 2.0, 3.0, 4.0)),
    )
    assert details["region_id"] == "r-1"

    perception = TinyTorchPerceptionModel(device="cpu", strict_runtime=True)
    perception_handle = perception.load("perception-v1")
    pred = perception.predict(perception_handle, PerceptionRequest(region_count=3))
    assert 0.0 <= pred["confidence"] <= 1.0
