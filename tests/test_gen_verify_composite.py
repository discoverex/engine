from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from discoverex.application.use_cases.gen_verify.composite_pipeline import (
    compose_scene,
    resolve_composite_image_ref,
)


def test_resolve_composite_falls_back_to_background_when_fx_output_missing() -> None:
    composite = resolve_composite_image_ref(
        background_asset_ref="assets/background.png",
        fx_prediction={},
    )
    assert composite.image_ref == "assets/background.png"
    assert composite.artifact_path is None


def test_resolve_composite_uses_existing_local_output_path(tmp_path) -> None:
    composed = tmp_path / "composite.png"
    composed.write_bytes(b"real-image-bytes")

    composite = resolve_composite_image_ref(
        background_asset_ref="assets/background.png",
        fx_prediction={"output_path": str(composed)},
    )
    assert composite.image_ref == str(composed)
    assert composite.artifact_path == composed


def test_compose_scene_passes_runtime_dimensions_to_fx(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class _FxModel:
        def predict(self, _handle, request):  # type: ignore[no-untyped-def]
            captured.update(request.params)
            output = Path(request.params["output_path"])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"img")
            return {"output_path": str(output)}

    context = SimpleNamespace(
        runtime=SimpleNamespace(
            width=320,
            height=240,
            model_runtime=SimpleNamespace(seed=11),
        ),
        fx_model=_FxModel(),
    )
    composite = compose_scene(
        context=context,
        background_asset_ref="bg://dummy",
        scene_dir=tmp_path,
        fx_handle=SimpleNamespace(),
    )

    assert captured["width"] == 320
    assert captured["height"] == 240
    assert captured["seed"] == 11
    assert composite.artifact_path is not None
