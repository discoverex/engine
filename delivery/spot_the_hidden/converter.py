from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from discoverex.domain.scene import Scene

from .schema import (
    AnswerKey,
    AnswerRegion,
    DeliveryMeta,
    GameBundle,
    HintItem,
    PlayableScene,
    RegionBBox,
    SceneRef,
    StorageType,
    UiFlags,
)


def _detect_storage(image_ref: str) -> StorageType:
    lower = image_ref.lower()
    if lower.startswith("s3://"):
        return StorageType.S3
    if lower.startswith("minio://") or "minio" in lower:
        return StorageType.MINIO
    return StorageType.LOCAL


def _image_meta(image_ref: str) -> tuple[str, str, int]:
    mime = mimetypes.guess_type(image_ref)[0] or "application/octet-stream"
    path = Path(image_ref)
    if not path.exists() or not path.is_file():
        return mime, "", 0
    data = path.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    return mime, checksum, len(data)


def _goal_text(scene: Scene) -> str | None:
    description = scene.goal.constraint_struct.get("description")
    if isinstance(description, str) and description:
        return description
    return scene.goal.goal_type.value


def extract_playable(scene: Scene) -> PlayableScene:
    hints = [HintItem(key="region_count", value=str(len(scene.regions)))]
    ui_flags = UiFlags(allow_multi_click=len(scene.answer.answer_region_ids) > 1)
    return PlayableScene(
        image_ref=scene.composite.final_image_ref,
        width=scene.background.width,
        height=scene.background.height,
        goal_text=_goal_text(scene),
        hints=hints,
        ui_flags=ui_flags,
    )


def extract_answer_key(scene: Scene) -> AnswerKey:
    answer_set = set(scene.answer.answer_region_ids)
    regions: list[AnswerRegion] = []
    for region in scene.regions:
        if region.region_id not in answer_set:
            continue
        regions.append(
            AnswerRegion(
                region_id=region.region_id,
                bbox=RegionBBox(
                    x=region.geometry.bbox.x,
                    y=region.geometry.bbox.y,
                    w=region.geometry.bbox.w,
                    h=region.geometry.bbox.h,
                ),
                role=region.role.value,
            )
        )
    return AnswerKey(answer_region_ids=scene.answer.answer_region_ids, regions=regions)


def build_game_bundle(scene: Scene, source_scene_json: str) -> GameBundle:
    image_ref = scene.composite.final_image_ref
    storage = _detect_storage(image_ref)
    image_mime, image_sha256, image_bytes = _image_meta(image_ref)
    return GameBundle(
        scene_ref=SceneRef(
            scene_id=scene.meta.scene_id,
            version_id=scene.meta.version_id,
            source_scene_json=source_scene_json,
        ),
        playable=extract_playable(scene),
        answer_key=extract_answer_key(scene),
        delivery_meta=DeliveryMeta(
            storage=storage,
            image_mime=image_mime,
            image_sha256=image_sha256,
            image_bytes=image_bytes,
            status=scene.meta.status.value,
            difficulty_score=scene.difficulty.estimated_score,
            created_at=scene.meta.created_at,
            model_versions=scene.meta.model_versions,
        ),
    )


def build_front_payload(bundle: GameBundle) -> dict[str, object]:
    payload = bundle.model_dump(mode="json")
    payload.pop("answer_key", None)
    return payload
