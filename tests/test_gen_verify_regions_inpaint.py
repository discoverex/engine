from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from discoverex.application.use_cases.gen_verify.objects.types import (
    GeneratedObjectAsset,
)
from discoverex.application.use_cases.gen_verify.regions.inpaint import generate_regions
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import Background


def test_generate_regions_chains_latest_composite_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_refs: list[str] = []
    barrier_stages: list[str] = []

    class _FakeInpaintModel:
        def predict(self, handle, request):
            _ = handle
            image_refs.append(str(request.image_ref))
            idx = len(image_refs)
            return {
                "composited_image_ref": str(tmp_path / f"composited-{idx}.png"),
                "selected_variant_ref": str(tmp_path / f"variant-{idx}.png"),
                "patch_image_ref": str(tmp_path / f"patch-{idx}.png"),
                "object_image_ref": request.object_image_ref,
                "object_mask_ref": request.object_mask_ref,
            }

    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.regions.inpaint.stage_gpu_barrier",
        lambda stage: barrier_stages.append(stage),
    )

    background = Background(
        asset_ref=str(tmp_path / "background.png"),
        width=512,
        height=512,
        metadata={},
    )
    regions = [
        Region(
            region_id=f"r-{index}",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=32.0, h=32.0)),
            role=RegionRole.ANSWER,
            source=RegionSource.CANDIDATE_MODEL,
            attributes={},
            version=1,
        )
        for index in range(1, 4)
    ]
    generated_objects = {
        region.region_id: GeneratedObjectAsset(
            region_id=region.region_id,
            candidate_ref=str(tmp_path / f"{region.region_id}.candidate.png"),
            object_ref=str(tmp_path / f"{region.region_id}.object.png"),
            object_mask_ref=str(tmp_path / f"{region.region_id}.mask.png"),
            width=32,
            height=32,
            object_prompt=f"object-{index}",
        )
        for index, region in enumerate(regions, start=1)
    }

    updated_regions, prompt_records = generate_regions(
        context=SimpleNamespace(inpaint_model=_FakeInpaintModel()),
        background=background,
        scene_dir=tmp_path,
        regions=regions,
        generated_objects=generated_objects,
        inpaint_handle=object(),
        object_prompt="alpha | beta | gamma",
        object_negative_prompt="blur",
    )

    assert len(updated_regions) == 3
    assert len(prompt_records) == 3
    assert image_refs == [
        str(tmp_path / "background.png"),
        str(tmp_path / "composited-1.png"),
        str(tmp_path / "composited-2.png"),
    ]
    assert background.metadata["inpaint_composited_ref"] == str(
        tmp_path / "composited-3.png"
    )
    assert barrier_stages == [
        "after_object_inpaint_01_r-1",
        "after_object_inpaint_02_r-2",
        "after_object_inpaint_03_r-3",
    ]
