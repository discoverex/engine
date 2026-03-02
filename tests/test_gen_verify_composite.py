from __future__ import annotations

from discoverex.application.use_cases.gen_verify.composite_pipeline import (
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
