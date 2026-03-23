from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from discoverex.application.use_cases.variantpack.replay import (
    build_replay_fixture_inputs,
    build_fixed_replay_inputs,
    has_replay_fixture_inputs,
    has_fixed_replay_inputs,
    replay_background_asset_ref,
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


def test_replay_fixture_inputs_materialize_selected_variant_assets(
    tmp_path: Path,
) -> None:
    background = tmp_path / "background.png"
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(background)
    coarse_variant = tmp_path / "variant.png"
    Image.new("RGBA", (12, 10), color=(255, 0, 0, 180)).save(coarse_variant)
    coarse_config = tmp_path / "variant.json"
    coarse_config.write_text(json.dumps({"variant_id": "v1"}), encoding="utf-8")
    coarse_selection = tmp_path / "coarse.selection.json"
    coarse_selection.write_text(
        json.dumps(
            {
                "selected_bbox": {"x": 1, "y": 2, "w": 12, "h": 10},
                "selected_variant_id": "v1",
            }
        ),
        encoding="utf-8",
    )
    fixture = tmp_path / "replay_fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "background_asset_ref": "background.png",
                "regions": [
                    {
                        "region_id": "r1",
                        "object_label": "glass",
                        "object_prompt": "glass",
                        "coarse_selected_bbox": {"x": 1, "y": 2, "w": 12, "h": 10},
                        "coarse_selection_ref": "coarse.selection.json",
                        "coarse_variant_image_ref": "variant.png",
                        "coarse_variant_config_ref": "variant.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert has_replay_fixture_inputs({"replay_fixture_ref": str(fixture)})
    assert replay_background_asset_ref({"replay_fixture_ref": str(fixture)}) == str(
        background.resolve()
    )

    regions, generated, loaded = build_replay_fixture_inputs(
        args={"replay_fixture_ref": str(fixture)},
        scene_dir=tmp_path / "scene",
        object_prompt="shared",
        object_negative_prompt="bad",
    )

    assert loaded["background_asset_ref"] == str(background.resolve())
    assert len(regions) == 1
    assert regions[0].attributes["patch_selection_coarse_ref"] == str(
        coarse_selection.resolve()
    )
    asset = generated["r1"]
    assert Path(asset.object_ref).exists()
    assert Path(asset.object_mask_ref).exists()
    assert asset.object_prompt == "glass"
