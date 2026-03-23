from __future__ import annotations

from datetime import datetime, timezone

from delivery.spot_the_hidden.converter import build_front_payload
from delivery.spot_the_hidden.schema import (
    AnswerAsset,
    AnswerKey,
    AnswerRegion,
    BackgroundImage,
    DeliveryMeta,
    GameBundle,
    PlayableScene,
    RegionBBox,
    SceneRef,
    StorageType,
)


def test_build_front_payload_does_not_expose_answer_key() -> None:
    bundle = GameBundle(
        scene_ref=SceneRef(
            scene_id="s", version_id="v", source_scene_json="scene.json"
        ),
        playable=PlayableScene(
            background_img=BackgroundImage(
                image_id="background",
                src="img.png",
                width=10,
                height=10,
            ),
            answers=[
                AnswerAsset(
                    lottie_id="lottie_01",
                    name="object 1",
                    src="object.png",
                    bbox=RegionBBox(x=1, y=1, w=2, h=2),
                    order=1,
                )
            ],
        ),
        answer_key=AnswerKey(
            answer_region_ids=["r1"],
            regions=[
                AnswerRegion(
                    region_id="r1",
                    bbox=RegionBBox(x=1, y=1, w=2, h=2),
                    role="answer",
                )
            ],
        ),
        delivery_meta=DeliveryMeta(
            storage=StorageType.LOCAL,
            image_mime="image/png",
            image_sha256="a" * 64,
            image_bytes=5,
            status="approved",
            difficulty_score=0.2,
            created_at=datetime.now(timezone.utc),
            model_versions={},
        ),
    )

    payload = build_front_payload(bundle)
    playable = payload["playable"]
    assert isinstance(playable, dict)
    playable_dict = playable
    assert "answer_key" not in payload
    assert playable_dict["background_img"]["src"] == "img.png"
    assert len(playable_dict["answers"]) == 1
