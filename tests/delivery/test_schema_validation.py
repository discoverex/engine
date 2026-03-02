from __future__ import annotations

from datetime import datetime, timezone

from delivery.spot_the_hidden.schema import (
    AnswerKey,
    AnswerRegion,
    DeliveryMeta,
    GameBundle,
    PlayableScene,
    RegionBBox,
    SceneRef,
    StorageType,
)


def test_game_bundle_pydantic_validation_roundtrip() -> None:
    bundle = GameBundle(
        scene_ref=SceneRef(scene_id="scene-1", version_id="v-1", source_scene_json="x"),
        playable=PlayableScene(image_ref="a.png", width=10, height=20),
        answer_key=AnswerKey(
            answer_region_ids=["r1"],
            regions=[
                AnswerRegion(
                    region_id="r1",
                    bbox=RegionBBox(x=1, y=2, w=3, h=4),
                    role="answer",
                )
            ],
        ),
        delivery_meta=DeliveryMeta(
            storage=StorageType.LOCAL,
            image_mime="image/png",
            image_sha256="a" * 64,
            image_bytes=123,
            status="approved",
            difficulty_score=0.2,
            created_at=datetime.now(timezone.utc),
            model_versions={"p": "v1"},
        ),
    )

    dumped = bundle.model_dump(mode="json")
    loaded = GameBundle.model_validate(dumped)
    assert loaded.scene_ref.scene_id == "scene-1"
    assert loaded.answer_key.regions[0].bbox.w == 3
