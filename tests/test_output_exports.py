from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from PIL import Image

from discoverex.application.use_cases.output_exports import export_output_bundle
from discoverex.domain.goal import AnswerForm, Goal, GoalType
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import (
    Answer,
    Background,
    Composite,
    Difficulty,
    LayerBBox,
    LayerItem,
    LayerStack,
    LayerType,
    Scene,
    SceneMeta,
    SceneStatus,
)
from discoverex.domain.verification import (
    FinalVerification,
    VerificationBundle,
    VerificationResult,
)


def test_export_output_bundle_writes_object_centric_outputs(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    scene_root = tmp_path / "scenes" / "scene-1" / "v1"
    metadata_dir = scene_root / "metadata"
    metadata_dir.mkdir(parents=True)
    scene_json_path = metadata_dir / "scene.json"
    verification_json_path = metadata_dir / "verification.json"
    scene_json_path.write_text("{}", encoding="utf-8")
    verification_json_path.write_text("{}", encoding="utf-8")

    base_image = scene_root / "assets" / "background" / "base.png"
    raw_generated_image = scene_root / "assets" / "objects" / "object.candidate.png"
    sam_object_image = scene_root / "assets" / "objects" / "object.sam.png"
    sam_object_mask = scene_root / "assets" / "masks" / "object.sam.mask.png"
    object_image = scene_root / "assets" / "objects" / "object.png"
    processed_object_image = scene_root / "assets" / "patches" / "object.layer.png"
    processed_object_mask = scene_root / "assets" / "patches" / "object.layer-mask.png"
    precomposite_image = scene_root / "assets" / "patches" / "region.precomposite.png"
    variant_manifest = scene_root / "assets" / "patches" / "region.variants.json"
    coarse_selection = scene_root / "assets" / "patch_selection" / "r1" / "coarse.selection.json"
    fine_selection = scene_root / "assets" / "patch_selection" / "r1" / "fine.selection.json"
    composite_image = scene_root / "outputs" / "composite.png"
    for path, color in (
        (base_image, (255, 255, 255, 255)),
        (raw_generated_image, (250, 80, 40, 255)),
        (sam_object_image, (220, 40, 120, 255)),
        (sam_object_mask, (255, 255, 255, 255)),
        (object_image, (255, 0, 0, 255)),
        (processed_object_image, (0, 0, 255, 255)),
        (processed_object_mask, (255, 255, 255, 255)),
        (precomposite_image, (0, 255, 0, 255)),
        (composite_image, (0, 0, 0, 255)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "L" if path in {sam_object_mask, processed_object_mask} else "RGBA"
        size = (10, 12) if path in {processed_object_image, processed_object_mask} else (64, 64)
        Image.new(mode, size, color=color[0] if mode == "L" else color).save(path)
    variant_manifest.write_text("{}", encoding="utf-8")
    coarse_selection.parent.mkdir(parents=True, exist_ok=True)
    coarse_selection.write_text("{}", encoding="utf-8")
    fine_selection.write_text("{}", encoding="utf-8")

    scene = Scene(
        meta=SceneMeta(
            scene_id="scene-1",
            version_id="v1",
            status=SceneStatus.APPROVED,
            pipeline_run_id="run-1",
            model_versions={},
            config_version="config-v1",
            created_at=now,
            updated_at=now,
        ),
        background=Background(
            asset_ref=str(base_image),
            width=64,
            height=64,
            metadata={
                "inpaint_layer_candidates": [
                    {
                        "region_id": "r1",
                        "candidate_image_ref": str(object_image),
                        "raw_generated_image_ref": str(raw_generated_image),
                        "sam_object_image_ref": str(sam_object_image),
                        "sam_object_mask_ref": str(sam_object_mask),
                        "object_image_ref": str(object_image),
                        "processed_object_image_ref": str(processed_object_image),
                        "processed_object_mask_ref": str(processed_object_mask),
                        "object_mask_ref": str(object_image),
                        "raw_alpha_mask_ref": str(object_image),
                        "patch_image_ref": str(object_image),
                        "precomposited_image_ref": str(precomposite_image),
                        "variant_manifest_ref": str(variant_manifest),
                        "patch_selection_coarse_ref": str(scene_root / "assets" / "patch_selection" / "r1" / "coarse.selection.json"),
                        "patch_selection_fine_ref": str(scene_root / "assets" / "patch_selection" / "r1" / "fine.selection.json"),
                        "layer_image_ref": str(processed_object_image),
                        "bbox": {"x": 1, "y": 2, "w": 10, "h": 12},
                        "object_prompt_resolved": "hidden brass key",
                        "object_negative_prompt_resolved": "blurry",
                    }
                ]
            },
        ),
        regions=[
            Region(
                region_id="r1",
                geometry=Geometry(type="bbox", bbox=BBox(x=1, y=2, w=10, h=12)),
                role=RegionRole.ANSWER,
                source=RegionSource.MANUAL,
                attributes={},
                version=1,
            )
        ],
        composite=Composite(final_image_ref=str(composite_image)),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id="layer-base",
                    type=LayerType.BASE,
                    image_ref=str(base_image),
                    z_index=0,
                    order=0,
                ),
                LayerItem(
                    layer_id="layer-object",
                    type=LayerType.INPAINT_PATCH,
                    image_ref=str(object_image),
                    bbox=LayerBBox(x=1, y=2, w=10, h=12),
                    z_index=10,
                    order=1,
                    source_region_id="r1",
                ),
                LayerItem(
                    layer_id="layer-final",
                    type=LayerType.FX_OVERLAY,
                    image_ref=str(composite_image),
                    z_index=100,
                    order=2,
                ),
            ]
        ),
        goal=Goal(
            goal_type=GoalType.RELATION,
            constraint_struct={},
            answer_form=AnswerForm.REGION_SELECT,
        ),
        answer=Answer(answer_region_ids=["r1"], uniqueness_intent=True),
        verification=VerificationBundle(
            logical=VerificationResult(score=1.0, pass_=True, signals={}),
            perception=VerificationResult(score=1.0, pass_=True, signals={}),
            final=FinalVerification(total_score=1.0, pass_=True, failure_reason=""),
        ),
        difficulty=Difficulty(estimated_score=0.1, source="rule_based"),
    )

    exported = export_output_bundle(artifacts_root=tmp_path, scene=scene)

    assert exported.background_path.exists()
    assert exported.manifest_path.exists()
    assert exported.delivery_manifest_path.exists()
    assert len(exported.object_png_paths) == 1
    assert len(exported.object_lottie_paths) == 1
    assert len(exported.original_paths) == 15
    assert len(exported.delivery_paths) >= 5
    payload = json.loads(exported.manifest_path.read_text(encoding="utf-8"))
    assert payload["scene_ref"] == {
        "title": "scene-1",
        "scene_id": "scene-1",
        "version_id": "v1",
    }
    assert payload["background_img"] == {
        "image_id": "background",
        "src": "background.png",
        "prompt": "",
        "width": 64,
        "height": 64,
    }
    assert payload["answers"] == [
        {
            "lottie_id": "lottie_01",
            "name": "hidden brass key | blurry",
            "title": "hidden brass key | blurry",
            "src": "object_01.png",
            "bbox": {"x": 1.0, "y": 2.0, "w": 10.0, "h": 12.0},
            "prompt": "hidden brass key",
            "order": 1,
        }
    ]
    assert {"region_id": "r1", "kind": "candidate_image_ref", "path": "original/r1/object.png"} in payload["original"]
    assert {"region_id": "r1", "kind": "raw_generated_image_ref", "path": "original/r1/object.candidate.png"} in payload["original"]
    assert {"region_id": "r1", "kind": "sam_object_image_ref", "path": "original/r1/object.sam.png"} in payload["original"]
    assert {"region_id": "r1", "kind": "sam_object_mask_ref", "path": "original/r1/object.sam.mask.png"} in payload["original"]
    assert {"region_id": "r1", "kind": "processed_object_image_ref", "path": "original/r1/object.layer.png"} in payload["original"]
    assert {"region_id": "r1", "kind": "processed_object_mask_ref", "path": "original/r1/object.layer-mask.png"} in payload["original"]
    assert {"region_id": "r1", "kind": "precomposited_image_ref", "path": "original/r1/region.precomposite.png"} in payload["original"]
    assert {"region_id": "r1", "kind": "variant_manifest_ref", "path": "original/r1/region.variants.json"} in payload["original"]
    assert {"region_id": "r1", "kind": "patch_selection_coarse_ref", "path": "original/r1/coarse.selection.json"} in payload["original"]
    assert {"region_id": "r1", "kind": "patch_selection_fine_ref", "path": "original/r1/fine.selection.json"} in payload["original"]
    assert {"region_id": "r1", "kind": "diagnostics", "path": "original/r1/diagnostics.json"} in payload["original"]
    assert (scene_root / "outputs" / "original" / "r1" / "object.png").exists()
    assert (scene_root / "outputs" / "original" / "r1" / "diagnostics.json").exists()
    delivery_manifest = json.loads(exported.delivery_manifest_path.read_text(encoding="utf-8"))
    assert delivery_manifest["scene_ref"]["title"] == "scene-1"
    assert delivery_manifest["background_img"]["src"] == "background/background.png"
    assert delivery_manifest["answers"][0]["src"] == "objects/object_01.png"
    assert (scene_root / "outputs" / "delivery" / "metadata" / "scene.json").exists()
    assert (scene_root / "outputs" / "delivery" / "metadata" / "verification.json").exists()
    assert (scene_root / "outputs" / "delivery" / "background" / "background.png").exists()
    assert (scene_root / "outputs" / "delivery" / "manifest.json").exists()
    assert (scene_root / "outputs" / "delivery" / "objects" / "object_01.png").exists()
    assert (scene_root / "outputs" / "delivery" / "objects" / "object_01.lottie").exists()
    with ZipFile(exported.object_lottie_paths[0]) as archive:
        names = set(archive.namelist())
        animation = json.loads(archive.read("animations/object_01.json").decode("utf-8"))
    assert "manifest.json" in names
    assert "animations/object_01.json" in names
    assert "images/object_01.png" in names
    assert animation["metadata"]["scene_id"] == "scene-1"
    assert animation["metadata"]["bbox"] == {"x": 1.0, "y": 2.0, "w": 10.0, "h": 12.0}
    assert animation["layers"][0]["nm"] == "hidden brass key | blurry"
    assert len(animation["layers"]) == 1
    assert Image.open(scene_root / "outputs" / "objects" / "object_01.png").getpixel((0, 0)) == (0, 0, 255, 255)
