from __future__ import annotations

from pathlib import Path

import pytest

from discoverex.adapters.outbound.models.hf_inpaint import HFInpaintModel
from discoverex.models.types import InpaintRequest, ModelHandle


def test_hf_inpaint_fast_patch_writes_patch_and_composite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    Image = pytest.importorskip("PIL.Image")

    source = tmp_path / "source.png"
    Image.new("RGB", (320, 240), color=(120, 120, 120)).save(source)

    model = HFInpaintModel(model_id="google/mobilenet_v2_1.0_224", strict_runtime=False)
    handle = ModelHandle(
        name="inpaint_model",
        version="v1",
        runtime="hf",
        device="cpu",
        dtype="float32",
        extra={"runtime_available": False},
    )

    def _fake_generate_patch(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return Image.new("RGB", (64, 64), color=(255, 0, 0))

    monkeypatch.setattr(model, "_generate_patch_with_diffusers", _fake_generate_patch)

    out = tmp_path / "composite.png"
    pred = model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r-1",
            bbox=(50.0, 60.0, 64.0, 64.0),
            output_path=str(out),
            prompt="repair",
        ),
    )

    assert pred["region_id"] == "r-1"
    assert pred["inpaint_mode"] == "fast_patch"
    assert isinstance(pred["quality_score"], float)
    assert Path(pred["patch_image_ref"]).exists()
    assert Path(pred["composited_image_ref"]).exists()
    assert out.exists()
