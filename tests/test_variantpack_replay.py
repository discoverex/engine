from __future__ import annotations

from pathlib import Path

from discoverex.application.use_cases.variantpack.replay import (
    build_fixed_replay_inputs,
    has_fixed_replay_inputs,
)


def test_has_fixed_replay_inputs_requires_object_mask_and_bbox() -> None:
    assert has_fixed_replay_inputs(
        {
            "object_image_ref": "/tmp/object.png",
            "object_mask_ref": "/tmp/object.mask.png",
            "bbox": {"x": 1, "y": 2, "w": 3, "h": 4},
        }
    )
    assert not has_fixed_replay_inputs(
        {
            "object_image_ref": "/tmp/object.png",
            "bbox": {"x": 1, "y": 2, "w": 3, "h": 4},
        }
    )


def test_build_fixed_replay_inputs_uses_fixed_assets(tmp_path: Path) -> None:
    object_ref = tmp_path / "fixed.selected.png"
    mask_ref = tmp_path / "fixed.selected.mask.png"
    raw_alpha_ref = tmp_path / "fixed.selected.raw-alpha-mask.png"
    for path in (object_ref, mask_ref, raw_alpha_ref):
        path.write_bytes(b"stub")

    regions, generated = build_fixed_replay_inputs(
        args={
            "region_id": "replay-1",
            "object_image_ref": str(object_ref),
            "object_mask_ref": str(mask_ref),
            "raw_alpha_mask_ref": str(raw_alpha_ref),
            "bbox": {"x": 10, "y": 20, "w": 30, "h": 40},
        },
        object_prompt="glass",
        object_negative_prompt="bad",
        object_model_id="model-x",
        object_sampler="sampler-y",
        object_steps=8,
        object_guidance_scale=1.5,
        object_seed=7,
    )

    assert len(regions) == 1
    region = regions[0]
    assert region.region_id == "replay-1"
    assert region.geometry.bbox.x == 10
    asset = generated["replay-1"]
    assert asset.object_ref == str(object_ref)
    assert asset.object_mask_ref == str(mask_ref)
    assert asset.raw_alpha_mask_ref == str(raw_alpha_ref)
    assert asset.original_object_ref == str(object_ref)
    assert asset.object_prompt == "glass"
    assert asset.object_model_id == "model-x"
