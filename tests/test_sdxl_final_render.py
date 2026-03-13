from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from discoverex.adapters.outbound.models.sdxl_final_render import SdxlFinalRenderModel
from discoverex.models.types import FxRequest, ModelHandle


def test_final_render_resizes_source_to_requested_dimensions(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}
    fake_torch = SimpleNamespace(
        Generator=lambda device="cpu": SimpleNamespace(manual_seed=lambda seed: ("seeded", device, seed))
    )

    class _FakePipe:
        def __call__(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return SimpleNamespace(images=[kwargs["image"]])

    source = tmp_path / "source.png"
    Image.new("RGB", (1024, 768), color="white").save(source)
    model = SdxlFinalRenderModel()
    monkeypatch.setattr(model, "_load_pipe", lambda _handle: _FakePipe())
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)

    output = model.predict(
        ModelHandle(name="fx", version="v1", runtime="sdxl"),
        FxRequest(
            image_ref=str(source),
            params={
                "output_path": str(tmp_path / "final.png"),
                "width": 512,
                "height": 512,
            },
        ),
    )

    assert output["output_path"].endswith("final.png")
    assert captured["width"] == 512
    assert captured["height"] == 512
    assert captured["image"].size == (512, 512)
