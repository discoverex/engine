from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from discoverex.application.use_cases.variantpack.fine_replay import (
    refine_replay_regions,
)
from discoverex.application.use_cases.variantpack.replay import (
    build_replay_fixture_inputs,
    build_fixed_replay_inputs,
    has_replay_fixture_inputs,
    has_fixed_replay_inputs,
    replay_background_asset_ref,
)
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import Background


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


def test_refine_replay_regions_skips_empty_patch_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    background_ref = tmp_path / "background.png"
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(background_ref)
    variant_ref = tmp_path / "variant.png"
    Image.new("RGBA", (8, 8), color=(255, 0, 0, 180)).save(variant_ref)
    config_ref = tmp_path / "variant.json"
    config_ref.write_text("{}", encoding="utf-8")
    region = Region(
        region_id="r1",
        geometry=Geometry(type="bbox", bbox=BBox(x=4.0, y=4.0, w=8.0, h=8.0)),
        role=RegionRole.ANSWER,
        source=RegionSource.MANUAL,
        attributes={
            "coarse_variant_image_ref": str(variant_ref),
            "coarse_variant_config_ref": str(config_ref),
            "selected_variant_id": "fixture-selected",
            "selected_variant_config": {},
        },
        version=1,
    )
    background = Background(asset_ref=str(background_ref), width=32, height=32, metadata={})
    config = SimpleNamespace(
        patch_similarity=SimpleNamespace(
            lab_weight=0.35,
            lbp_weight=0.2,
            gabor_weight=0.0,
            hog_weight=0.25,
        ),
        region_selection=SimpleNamespace(iou_threshold=0.12),
    )

    monkeypatch.setattr(
        "discoverex.application.use_cases.variantpack.fine_replay._iter_local_refined_bboxes",
        lambda *args, **kwargs: [(-100.0, -100.0, 8.0, 8.0), (4.0, 4.0, 8.0, 8.0)],
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.variantpack.fine_replay._extract_feature_bundle",
        lambda image, **kwargs: {"lab": [1.0]},
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.variantpack.fine_replay._score_feature_bundle",
        lambda **kwargs: {"lab": 0.5},
    )

    refined = refine_replay_regions(
        config=config,
        scene_dir=tmp_path / "scene",
        background=background,
        regions=[region],
    )

    assert len(refined) == 1
    assert refined[0].geometry.bbox.x == 4.0
    assert refined[0].attributes["selection_strategy"] == "replay_fixture_fine"
