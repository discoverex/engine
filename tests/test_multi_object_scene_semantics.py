from __future__ import annotations

from types import SimpleNamespace

from discoverex.application.use_cases.gen_verify.scene_builder import build_scene
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
from discoverex.domain.services.verification import run_logical_verification
from discoverex.domain.verification import (
    FinalVerification,
    VerificationBundle,
    VerificationResult,
)


def test_build_scene_marks_all_regions_as_answers() -> None:
    background = Background(asset_ref="bg.png", width=512, height=512)
    regions = [
        Region(
            region_id=f"r-{index}",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=32.0, h=32.0)),
            role=RegionRole.ANSWER,
            source=RegionSource.INPAINT,
            attributes={},
            version=1,
        )
        for index in range(1, 4)
    ]

    scene = build_scene(
        background=background,
        regions=regions,
        model_versions={},
        runtime_cfg=SimpleNamespace(config_version="cfg-v1"),
        run_ids=SimpleNamespace(
            scene_id="scene-1",
            version_id="v1",
            pipeline_run_id="run-1",
        ),
    )

    assert scene.answer.answer_region_ids == ["r-1", "r-2", "r-3"]
    assert scene.goal.answer_form == AnswerForm.REGION_SELECT
    assert scene.goal.constraint_struct["description"] == "find every hidden object region in the scene"


def test_run_logical_verification_accepts_multi_object_answers() -> None:
    scene = Scene(
        meta=SceneMeta(
            scene_id="scene-1",
            version_id="v1",
            status=SceneStatus.CANDIDATE,
            pipeline_run_id="run-1",
            model_versions={},
            config_version="cfg-v1",
        ),
        background=Background(asset_ref="bg.png", width=256, height=256),
        regions=[
            Region(
                region_id="r-1",
                geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=16.0, h=16.0)),
                role=RegionRole.ANSWER,
                source=RegionSource.INPAINT,
                attributes={},
                version=1,
            ),
            Region(
                region_id="r-2",
                geometry=Geometry(type="bbox", bbox=BBox(x=20.0, y=20.0, w=16.0, h=16.0)),
                role=RegionRole.ANSWER,
                source=RegionSource.INPAINT,
                attributes={},
                version=1,
            ),
        ],
        composite=Composite(final_image_ref="final.png"),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id="layer-base",
                    type=LayerType.BASE,
                    image_ref="bg.png",
                    order=0,
                )
            ]
        ),
        goal=Goal(
            goal_type=GoalType.RELATION,
            constraint_struct={"description": "find every hidden object region in the scene"},
            answer_form=AnswerForm.REGION_SELECT,
        ),
        answer=Answer(answer_region_ids=["r-1", "r-2"], uniqueness_intent=True),
        verification=VerificationBundle(
            logical=VerificationResult(score=0.0, pass_=False, signals={}),
            perception=VerificationResult(score=0.0, pass_=False, signals={}),
            final=FinalVerification(total_score=0.0, pass_=False, failure_reason=""),
        ),
        difficulty=Difficulty(estimated_score=0.0, source="rule_based"),
    )

    result = run_logical_verification(scene, pass_threshold=0.9)

    assert result.pass_ is True
    assert result.score == 1.0
    assert result.signals["multi_object_ok"] is True
