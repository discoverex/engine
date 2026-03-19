from __future__ import annotations

from pathlib import Path
from typing import cast

from PIL import Image, ImageDraw

from discoverex.application.use_cases.naturalness_evaluation import (
    collect_naturalness_inputs,
    evaluate_naturalness_inputs,
    evaluate_scene_naturalness,
)
from discoverex.domain.goal import AnswerForm, Goal, GoalType
from discoverex.domain.naturalness import NaturalnessRegionInput, SelectedBBox
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


def test_evaluate_naturalness_inputs_prefers_higher_scores_for_blended_region(
    tmp_path: Path,
) -> None:
    blended = tmp_path / "blended.png"
    harsh = tmp_path / "harsh.png"
    _make_scene_image(blended, object_fill=(122, 132, 142), outline=(122, 132, 142))
    _make_scene_image(harsh, object_fill=(255, 0, 0), outline=(255, 255, 255))

    bbox = cast(SelectedBBox, {"x": 28.0, "y": 28.0, "w": 24.0, "h": 24.0})
    blended_score = evaluate_naturalness_inputs(
        [
            NaturalnessRegionInput(
                region_id="r-blended",
                final_image_ref=str(blended),
                selected_bbox=bbox,
                placement_score=0.92,
            )
        ]
    )
    harsh_score = evaluate_naturalness_inputs(
        [
            NaturalnessRegionInput(
                region_id="r-harsh",
                final_image_ref=str(harsh),
                selected_bbox=bbox,
                placement_score=0.35,
            )
        ]
    )

    assert blended_score.overall_score > harsh_score.overall_score
    assert (
        blended_score.regions[0].seam_visibility
        < harsh_score.regions[0].seam_visibility
    )
    assert blended_score.regions[0].saliency_lift < harsh_score.regions[0].saliency_lift


def test_collect_naturalness_inputs_reads_region_attributes(tmp_path: Path) -> None:
    final_image = tmp_path / "scene.png"
    Image.new("RGB", (64, 64), color=(128, 128, 128)).save(final_image)
    scene = _build_scene(
        final_image=str(final_image),
        region_attributes={
            "selected_bbox": {"x": 10.0, "y": 12.0, "w": 14.0, "h": 16.0},
            "object_image_ref": str(tmp_path / "object.png"),
            "object_mask_ref": str(tmp_path / "mask.png"),
            "patch_image_ref": str(tmp_path / "patch.png"),
            "placement_score": 0.77,
        },
    )

    inputs = collect_naturalness_inputs(scene)

    assert len(inputs) == 1
    assert inputs[0].selected_bbox["x"] == 10.0
    assert inputs[0].placement_score == 0.77
    assert inputs[0].object_mask_ref == str(tmp_path / "mask.png")


def test_evaluate_scene_naturalness_uses_scene_metadata(tmp_path: Path) -> None:
    final_image = tmp_path / "scene-final.png"
    _make_scene_image(final_image, object_fill=(126, 126, 126), outline=(126, 126, 126))
    scene = _build_scene(
        final_image=str(final_image),
        region_attributes={
            "selected_bbox": {"x": 28.0, "y": 28.0, "w": 24.0, "h": 24.0},
            "placement_score": 0.88,
        },
    )

    result = evaluate_scene_naturalness(scene)

    assert result.scene_id == "scene-1"
    assert result.version_id == "v-1"
    assert result.summary["region_count"] == 1
    assert 0.0 <= result.overall_score <= 1.0


def _make_scene_image(
    path: Path, *, object_fill: tuple[int, int, int], outline: tuple[int, int, int]
) -> None:
    image = Image.new("RGB", (80, 80), color=(120, 130, 140))
    draw = ImageDraw.Draw(image)
    draw.rectangle((28, 28, 52, 52), fill=object_fill, outline=outline, width=3)
    image.save(path)


def _build_scene(*, final_image: str, region_attributes: dict[str, object]) -> Scene:
    region = Region(
        region_id="r-1",
        geometry=Geometry(bbox=BBox(x=28.0, y=28.0, w=24.0, h=24.0)),
        role=RegionRole.ANSWER,
        source=RegionSource.INPAINT,
        attributes=region_attributes,
        version=1,
    )
    return Scene(
        meta=SceneMeta(
            scene_id="scene-1",
            version_id="v-1",
            status=SceneStatus.CANDIDATE,
            pipeline_run_id="run-1",
            model_versions={"inpaint": "test"},
            config_version="test",
        ),
        background=Background(asset_ref=final_image, width=80, height=80),
        regions=[region],
        composite=Composite(final_image_ref=final_image),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id="base",
                    type=LayerType.BASE,
                    image_ref=final_image,
                    order=1,
                )
            ]
        ),
        goal=Goal(
            goal_type=GoalType.SEMANTIC,
            constraint_struct={"description": "find hidden object"},
            answer_form=AnswerForm.REGION_SELECT,
        ),
        answer=Answer(answer_region_ids=["r-1"]),
        verification=VerificationBundle(
            logical=VerificationResult(score=1.0, pass_=True, signals={}),
            perception=VerificationResult(score=1.0, pass_=True, signals={}),
            final=FinalVerification(total_score=1.0, pass_=True, failure_reason=""),
        ),
        difficulty=Difficulty(estimated_score=0.0, source="test"),
    )
