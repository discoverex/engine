from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

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
from PIL import Image


def test_export_output_bundle_writes_lottie_and_output_layers(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    scene_root = tmp_path / "scenes" / "scene-1" / "v1"
    metadata_dir = scene_root / "metadata"
    metadata_dir.mkdir(parents=True)
    scene_json_path = metadata_dir / "scene.json"
    verification_json_path = metadata_dir / "verification.json"
    scene_json_path.write_text("{}", encoding="utf-8")
    verification_json_path.write_text("{}", encoding="utf-8")

    base_image = scene_root / "assets" / "background" / "base.png"
    object_image = scene_root / "assets" / "objects" / "object.png"
    composite_image = scene_root / "outputs" / "composite.png"
    for path, color in (
        (base_image, (255, 255, 255, 255)),
        (object_image, (255, 0, 0, 255)),
        (composite_image, (0, 0, 0, 255)),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (64, 64), color=color).save(path)

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
                        "object_image_ref": str(object_image),
                        "object_mask_ref": str(object_image),
                        "patch_image_ref": str(object_image),
                        "layer_image_ref": str(object_image),
                        "bbox": {"x": 1, "y": 2, "w": 10, "h": 12},
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

    assert exported.lottie_path.exists()
    assert exported.manifest_path.exists()
    assert len(exported.layer_paths) == 3
    assert len(exported.source_layer_paths) == 1
    payload = json.loads(exported.manifest_path.read_text(encoding="utf-8"))
    assert payload["lottie_path"] == "animation.lottie"
    assert payload["source_layers"] == [{"path": "layers/source-objects/001-layer-object.png"}]
    assert payload["object_entries"] == [
        {
            "object_number": 1,
            "layer_id": "layer-object",
            "region_id": "r1",
            "center": [6.0, 8.0],
            "bbox": {"x": 1.0, "y": 2.0, "w": 10.0, "h": 12.0},
        }
    ]
    assert payload["object_sources"] == [
        {
            "region_id": "r1",
            "object_number": 1,
            "center": [6.0, 8.0],
            "candidate_image_ref": str(object_image),
            "object_image_ref": str(object_image),
            "layer_image_ref": str(object_image),
            "object_mask_ref": str(object_image),
            "patch_image_ref": str(object_image),
        }
    ]
    assert [layer["layer_id"] for layer in payload["layers"]] == [
        "layer-base",
        "layer-object",
        "layer-final",
    ]
    assert payload["layers"][1]["object_number"] == 1
    assert payload["layers"][1]["center"] == [6.0, 8.0]
    assert payload["layers"][1]["description"] == "aligned object render with alpha"
    with ZipFile(exported.lottie_path) as archive:
        names = set(archive.namelist())
        animation = json.loads(archive.read("animations/scene.json").decode("utf-8"))
    assert "manifest.json" in names
    assert "animations/scene.json" in names
    assert "images/000-layer-base.png" in names
    assert "images/001-layer-object.png" in names
    assert "images/002-layer-final.png" in names
    assert animation["metadata"]["scene_id"] == "scene-1"
    assert animation["metadata"]["object_entries"] == payload["object_entries"]
    assert animation["layers"][1]["nm"] == "object 1 center=(6.0, 8.0)"
    assert len(animation["layers"]) == 3
