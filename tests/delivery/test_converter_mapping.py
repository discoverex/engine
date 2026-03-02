from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from delivery.spot_the_hidden.converter import build_game_bundle
from discoverex.domain.goal import AnswerForm, Goal, GoalType
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import (
    Answer,
    Background,
    Composite,
    Difficulty,
    Scene,
    SceneMeta,
    SceneStatus,
)
from discoverex.domain.verification import (
    FinalVerification,
    VerificationBundle,
    VerificationResult,
)


def _sample_scene(tmp_path: Path) -> Scene:
    image = tmp_path / "composite.png"
    image.write_bytes(b"png-bytes")
    now = datetime.now(timezone.utc)
    regions = [
        Region(
            region_id="r-answer",
            geometry=Geometry(type="bbox", bbox=BBox(x=10, y=20, w=30, h=40)),
            role=RegionRole.ANSWER,
            source=RegionSource.INPAINT,
            attributes={},
            version=1,
        ),
        Region(
            region_id="r-candidate",
            geometry=Geometry(type="bbox", bbox=BBox(x=50, y=60, w=20, h=20)),
            role=RegionRole.CANDIDATE,
            source=RegionSource.CANDIDATE_MODEL,
            attributes={},
            version=1,
        ),
    ]
    return Scene(
        meta=SceneMeta(
            scene_id="scene-1",
            version_id="v-1",
            status=SceneStatus.APPROVED,
            pipeline_run_id="run-1",
            model_versions={"perception": "p-v1"},
            config_version="config-v1",
            created_at=now,
            updated_at=now,
        ),
        background=Background(asset_ref="bg://sample", width=100, height=80),
        regions=regions,
        composite=Composite(final_image_ref=str(image)),
        goal=Goal(
            goal_type=GoalType.RELATION,
            constraint_struct={"description": "find the hidden object"},
            answer_form=AnswerForm.CLICK_ONE,
        ),
        answer=Answer(answer_region_ids=["r-answer"], uniqueness_intent=True),
        verification=VerificationBundle(
            logical=VerificationResult(score=0.8, pass_=True, signals={}),
            perception=VerificationResult(score=0.9, pass_=True, signals={}),
            final=FinalVerification(total_score=0.85, pass_=True, failure_reason=""),
        ),
        difficulty=Difficulty(estimated_score=0.25, source="rule_based"),
    )


def test_build_game_bundle_maps_scene_to_delivery_schema(tmp_path: Path) -> None:
    scene = _sample_scene(tmp_path)
    bundle = build_game_bundle(scene=scene, source_scene_json="scene.json")

    assert bundle.bundle_version == "spot_hidden_v1"
    assert bundle.scene_ref.scene_id == "scene-1"
    assert bundle.playable.width == 100
    assert bundle.playable.image_ref == scene.composite.final_image_ref
    assert bundle.answer_key.answer_region_ids == ["r-answer"]
    assert len(bundle.answer_key.regions) == 1
    assert bundle.delivery_meta.image_sha256
    assert bundle.delivery_meta.image_bytes > 0
