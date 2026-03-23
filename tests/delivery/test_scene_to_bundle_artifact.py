from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from delivery.spot_the_hidden.io import (
    convert_scene_json_to_bundle,
    default_bundle_path,
)
from delivery.spot_the_hidden.schema import GameBundle
from discoverex.domain.goal import AnswerForm, Goal, GoalType
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import (
    Answer,
    Background,
    Composite,
    Difficulty,
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


def _scene_json(tmp_path: Path) -> Path:
    image = tmp_path / "composite.png"
    image.write_bytes(b"x")
    now = datetime.now(timezone.utc)
    scene = Scene(
        meta=SceneMeta(
            scene_id="scene-2",
            version_id="v-2",
            status=SceneStatus.APPROVED,
            pipeline_run_id="run-2",
            model_versions={},
            config_version="config-v1",
            created_at=now,
            updated_at=now,
        ),
        background=Background(asset_ref="bg://sample", width=40, height=30),
        regions=[
            Region(
                region_id="r1",
                geometry=Geometry(type="bbox", bbox=BBox(x=1, y=2, w=3, h=4)),
                role=RegionRole.ANSWER,
                source=RegionSource.MANUAL,
                attributes={},
                version=1,
            )
        ],
        composite=Composite(final_image_ref=str(image)),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id="layer-base",
                    type=LayerType.BASE,
                    image_ref="bg://sample",
                    z_index=0,
                    order=0,
                ),
                LayerItem(
                    layer_id="layer-fx",
                    type=LayerType.FX_OVERLAY,
                    image_ref=str(image),
                    z_index=100,
                    order=1,
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
    path = tmp_path / "scene.json"
    path.write_text(scene.model_dump_json(by_alias=True), encoding="utf-8")
    return path


def test_convert_scene_json_to_bundle_writes_delivery_artifact(tmp_path: Path) -> None:
    scene_json = _scene_json(tmp_path)
    bundle_path = convert_scene_json_to_bundle(scene_json)

    assert bundle_path == default_bundle_path(scene_json)
    assert bundle_path.exists()

    bundle = GameBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    assert bundle.bundle_version == "spot_hidden_v3"
    assert bundle.scene_ref.scene_id == "scene-2"
    assert bundle.answer_key.answer_region_ids == ["r1"]
