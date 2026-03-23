from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from discoverex.application.use_cases.gen_verify.objects.service import (
    generate_region_objects,
)
from discoverex.application.use_cases.gen_verify.objects.types import (
    GeneratedObjectAsset,
)
from discoverex.application.use_cases.gen_verify.types import RegionPromptRecord
from discoverex.application.use_cases.generate_verify_v2 import (
    _apply_object_background_scaling,
    _bucket_patch_size,
    _build_background,
    _build_object_variants,
    _crop_object_for_patch_selection,
    _load_object_image_for_patch_selection,
    _tight_crop_variant_for_patch_selection,
    _find_best_patch,
    _generate_objects,
    _harmonize_rgba,
    _mark_regions_as_answers,
    _validate_generated_object_assets,
    _validate_region_outputs,
    _write_patch_selection_artifacts,
)
from discoverex.config_loader import load_pipeline_config
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import Background


def test_generate_verify_v2_config_loads() -> None:
    cfg = load_pipeline_config("generate", overrides=["flows/generate=generate_verify_v2"])
    assert cfg.flows is not None
    assert cfg.flows.generate.target == "discoverex.flows.subflows.generate_verify_v2"
    assert cfg.region_selection.strategy == "patch_similarity_v2"


def test_build_object_variants_respects_limit(tmp_path: Path) -> None:
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGBA", (32, 24), (240, 120, 80, 255)).save(object_path)
    Image.new("L", (32, 24), 255).save(mask_path)
    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=32,
        height=24,
    )
    cfg = load_pipeline_config("generate", overrides=["flows/generate=generate_verify_v2"])
    variants = _build_object_variants(config=cfg, asset=asset)
    assert 1 <= len(variants) <= cfg.object_variants.max_variants_per_object


def test_crop_object_for_patch_selection_uses_tight_bbox(tmp_path: Path) -> None:
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    for x in range(48, 80):
        for y in range(40, 72):
            image.putpixel((x, y), (240, 120, 80, 255))
    image.save(object_path)
    Image.new("L", (128, 128), 255).save(mask_path)
    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=32,
        height=32,
        tight_bbox=(48, 40, 80, 72),
    )
    with Image.open(object_path).convert("RGBA") as object_image:
        cropped = _crop_object_for_patch_selection(object_image=object_image, asset=asset)
    assert cropped.size == (32, 32)


def test_tight_crop_variant_for_patch_selection_uses_alpha_bbox() -> None:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(20, 44):
        for y in range(16, 40):
            image.putpixel((x, y), (240, 120, 80, 255))

    cropped = _tight_crop_variant_for_patch_selection(image)

    assert cropped.size == (24, 24)


def test_load_object_image_for_patch_selection_uses_object_alpha(
    tmp_path: Path,
) -> None:
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    for x in range(32, 96):
        for y in range(24, 104):
            image.putpixel((x, y), (240, 120, 80, 255))
    image.save(object_path)
    mask = Image.new("L", (128, 128), 0)
    for x in range(48, 80):
        for y in range(40, 72):
            mask.putpixel((x, y), 255)
    mask.save(mask_path)

    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=32,
        height=32,
    )

    with _load_object_image_for_patch_selection(asset) as image:
        assert image.getchannel("A").getbbox() == (32, 24, 96, 104)


def test_find_best_patch_returns_bbox_for_synthetic_background(tmp_path: Path) -> None:
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGBA", (24, 24), (180, 30, 30, 255)).save(object_path)
    Image.new("L", (24, 24), 255).save(mask_path)
    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=24,
        height=24,
    )
    cfg = load_pipeline_config(
        "generate",
        overrides=[
            "flows/generate=generate_verify_v2",
            "patch_similarity.min_patch_side=8",
            "region_selection.scale_factors=[1.0]",
            "region_selection.stride_ratio=0.5",
        ],
    )
    variants = _build_object_variants(config=cfg, asset=asset)[:1]
    background = Image.new("RGB", (96, 96), (30, 30, 180))
    result = _find_best_patch(
        config=cfg,
        background_image=__import__("numpy").asarray(background),
        variants=variants,
        selected_boxes=[],
    )
    assert result["score"] >= 0.0
    assert len(result["bbox"]) == 4
    assert len(result["coarse_bbox"]) == 4
    assert isinstance(result["variant_config"], dict)


def test_write_patch_selection_artifacts_persists_stage_json_and_variant_assets(
    tmp_path: Path,
) -> None:
    variant = {
        "variant_id": "rot0-scale1.00-base",
        "variant_config": {
            "rotation_deg": 0.0,
            "scale_factor": 1.0,
            "appearance_variant_id": "base",
            "saturation_mul": 1.0,
            "contrast_mul": 1.0,
            "sharpness_mul": 1.0,
        },
        "image": Image.new("RGBA", (16, 12), (240, 120, 80, 255)),
    }
    best = {
        "variant_id": variant["variant_id"],
        "variant_config": variant["variant_config"],
        "selection_strategy": "primary",
        "coarse_bbox": (10.0, 12.0, 16.0, 12.0),
        "bbox": (11.0, 14.0, 16.0, 12.0),
        "score": 0.88,
        "coarse_feature_scores": {"lab": 0.5, "lbp": 0.2},
        "feature_scores": {"lab": 0.5, "lbp": 0.2, "hog": 0.1, "gabor": 0.08},
    }

    paths = _write_patch_selection_artifacts(
        scene_dir=tmp_path,
        region_id="r-1",
        best=best,
        variant=variant,
    )

    coarse = json.loads(Path(paths["patch_selection_coarse_ref"]).read_text(encoding="utf-8"))
    fine = json.loads(Path(paths["patch_selection_fine_ref"]).read_text(encoding="utf-8"))

    assert coarse["stage"] == "coarse"
    assert coarse["selected_bbox"] == {"x": 10.0, "y": 12.0, "w": 16.0, "h": 12.0}
    assert Path(coarse["variant_image_ref"]).exists()
    assert Path(coarse["variant_config_ref"]).exists()
    assert fine["stage"] == "fine"
    assert fine["selected_bbox"] == {"x": 11.0, "y": 14.0, "w": 16.0, "h": 12.0}
    assert fine["feature_scores"]["hog"] == 0.1


def test_build_object_variants_scales_before_tight_crop(tmp_path: Path) -> None:
    background_path = tmp_path / "background.png"
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGB", (512, 512), (10, 20, 30)).save(background_path)
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    for x in range(200, 260):
        for y in range(220, 280):
            image.putpixel((x, y), (240, 120, 80, 255))
    image.save(object_path)
    mask = Image.new("L", (512, 512), 0)
    for x in range(200, 260):
        for y in range(220, 280):
            mask.putpixel((x, y), 255)
    mask.save(mask_path)
    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=60,
        height=60,
        tight_bbox=(200, 220, 260, 280),
    )
    cfg = load_pipeline_config(
        "generate",
        overrides=[
            "flows/generate=generate_verify_v2",
            "object_variants.rotation_degrees=[0.0]",
            "object_variants.obj_bg_ratio=0.1",
            "object_variants.scale_factors=[1.0]",
            "object_variants.canvas_padding=0",
            "object_variants.max_variants_per_object=1",
        ],
    )

    scaled = _apply_object_background_scaling(
        config=cfg,
        scene_dir=tmp_path,
        background=Background(
            asset_ref=str(background_path),
            width=512,
            height=512,
            metadata={},
        ),
        generated_objects={"r-1": asset},
    )
    variants = _build_object_variants(config=cfg, asset=scaled["r-1"])

    assert len(variants) == 1
    assert variants[0]["image"].size[0] <= 16
    assert variants[0]["image"].size[1] <= 16


def test_find_best_patch_uses_fallback_relaxation_when_primary_has_no_candidates(
    tmp_path: Path,
) -> None:
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGBA", (40, 40), (180, 30, 30, 255)).save(object_path)
    Image.new("L", (40, 40), 255).save(mask_path)
    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=40,
        height=40,
    )
    cfg = load_pipeline_config(
        "generate",
        overrides=[
            "flows/generate=generate_verify_v2",
            "patch_similarity.min_patch_side=8",
            "region_selection.scale_factors=[1.0]",
            "region_selection.fallback_scale_factors=[1.0]",
            "region_selection.iou_threshold=0.01",
            "region_selection.fallback_iou_threshold=0.8",
            "region_selection.stride_ratio=0.5",
        ],
    )
    variants = _build_object_variants(config=cfg, asset=asset)[:1]
    background = Image.new("RGB", (96, 96), (30, 30, 180))
    selected_boxes = [
        (0.0, 0.0, 32.0, 32.0),
        (32.0, 0.0, 32.0, 32.0),
        (64.0, 0.0, 32.0, 32.0),
        (0.0, 32.0, 32.0, 32.0),
        (32.0, 32.0, 32.0, 32.0),
        (64.0, 32.0, 32.0, 32.0),
        (0.0, 64.0, 32.0, 32.0),
        (32.0, 64.0, 32.0, 32.0),
        (64.0, 64.0, 32.0, 32.0),
    ]

    result = _find_best_patch(
        config=cfg,
        background_image=__import__("numpy").asarray(background),
        variants=variants,
        selected_boxes=selected_boxes,
    )

    assert result["score"] >= 0.0
    assert result["selection_strategy"] == "fallback"


def test_bucket_patch_size_quantizes_for_candidate_cache() -> None:
    cfg = load_pipeline_config(
        "generate",
        overrides=[
            "flows/generate=generate_verify_v2",
            "patch_similarity.min_patch_side=48",
        ],
    )
    assert _bucket_patch_size((101, 117), config=cfg) == (96, 120)


def test_find_best_patch_skips_gabor_when_weight_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGBA", (24, 24), (180, 30, 30, 255)).save(object_path)
    Image.new("L", (24, 24), 255).save(mask_path)
    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=24,
        height=24,
    )
    cfg = load_pipeline_config(
        "generate",
        overrides=[
            "flows/generate=generate_verify_v2",
            "patch_similarity.min_patch_side=8",
            "patch_similarity.gabor_weight=0.0",
            "patch_similarity.top_k_candidates=4",
            "region_selection.scale_factors=[1.0]",
            "region_selection.stride_ratio=0.5",
        ],
    )
    variants = _build_object_variants(config=cfg, asset=asset)[:1]
    background = Image.new("RGB", (96, 96), (30, 30, 180))

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_verify_v2._gabor_features",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("gabor should not run")
        ),
    )

    result = _find_best_patch(
        config=cfg,
        background_image=__import__("numpy").asarray(background),
        variants=variants,
        selected_boxes=[],
    )
    assert result["score"] >= 0.0


def test_apply_object_background_scaling_rewrites_object_assets(tmp_path: Path) -> None:
    background_path = tmp_path / "background.png"
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"

    Image.new("RGB", (512, 512), (10, 20, 30)).save(background_path)
    Image.new("RGBA", (512, 512), (180, 30, 30, 255)).save(object_path)
    Image.new("L", (512, 512), 255).save(mask_path)

    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        raw_alpha_mask_ref=str(mask_path),
        width=512,
        height=512,
    )
    cfg = load_pipeline_config(
        "generate",
        overrides=[
            "flows/generate=generate_verify_v2",
            "object_variants.obj_bg_ratio=0.1",
        ],
    )
    background = Background(asset_ref=str(background_path), width=512, height=512, metadata={})

    scaled = _apply_object_background_scaling(
        config=cfg,
        scene_dir=tmp_path,
        background=background,
        generated_objects={"r-1": asset},
    )

    scaled_asset = scaled["r-1"]
    with Image.open(scaled_asset.object_ref).convert("RGBA") as scaled_object:
        assert scaled_object.size == (51, 51)
    with Image.open(scaled_asset.object_mask_ref).convert("L") as scaled_mask:
        assert scaled_mask.size == (51, 51)
    assert scaled_asset.width == 51
    assert scaled_asset.height == 51
    assert scaled_asset.original_object_ref == str(object_path)
    assert scaled_asset.original_object_mask_ref == str(mask_path)
    assert scaled_asset.original_raw_alpha_mask_ref == str(mask_path)


def test_harmonize_rgba_preserves_alpha() -> None:
    rgba = Image.new("RGBA", (16, 16), (220, 50, 50, 200))
    patch = __import__("numpy").full((16, 16, 3), 120, dtype="uint8")
    harmonized = _harmonize_rgba(rgba=rgba, patch=patch, alpha=0.5)
    assert harmonized.mode == "RGBA"
    assert harmonized.getchannel("A").getextrema() == (200, 200)


def test_generate_objects_loads_model_once_and_passes_base_prompts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    regions = [
        Region(
            region_id="r-1",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=64.0, h=64.0)),
            role=RegionRole.ANSWER,
            source=RegionSource.MANUAL,
            attributes={},
            version=1,
        ),
        Region(
            region_id="r-2",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=64.0, h=64.0)),
            role=RegionRole.CANDIDATE,
            source=RegionSource.MANUAL,
            attributes={},
            version=1,
        ),
    ]
    captured: dict[str, object] = {}
    events: list[str] = []

    context = SimpleNamespace(
        object_generator_model=SimpleNamespace(
            load=lambda version: events.append(f"load:{version}") or SimpleNamespace(),
        ),
        model_versions=SimpleNamespace(object_generator="object-generator-v1"),
    )

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_verify_v2.generate_region_objects",
        lambda **kwargs: captured.update(kwargs)
        or {
            region.region_id: GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=str(tmp_path / f"{region.region_id}.png"),
                object_ref=str(tmp_path / f"{region.region_id}.object.png"),
                object_mask_ref=str(tmp_path / f"{region.region_id}.mask.png"),
                width=64,
                height=64,
            )
            for region in kwargs["regions"]
        },
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_verify_v2.unload_model",
        lambda model: events.append("unload"),
    )

    result = _generate_objects(
        context=context,
        scene_dir=tmp_path,
        regions=regions,
        object_prompt="butterfly | brass key",
        object_negative_prompt="blurry",
        object_base_prompt="isolated single object on transparent background",
        object_base_negative_prompt="opaque background, scene",
        object_generation_size=512,
    )

    assert list(result.keys()) == ["r-1", "r-2"]
    assert events == ["load:object-generator-v1", "unload"]
    assert captured["regions"] == regions
    assert captured["object_prompt"] == "butterfly | brass key"
    assert captured["object_negative_prompt"] == "blurry"
    assert (
        captured["object_base_prompt"]
        == "isolated single object on transparent background"
    )
    assert captured["object_base_negative_prompt"] == "opaque background, scene"


def test_find_best_patch_error_includes_diagnostics(tmp_path: Path) -> None:
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    Image.new("RGBA", (40, 40), (180, 30, 30, 255)).save(object_path)
    Image.new("L", (40, 40), 255).save(mask_path)
    asset = GeneratedObjectAsset(
        region_id="r-1",
        candidate_ref=str(object_path),
        object_ref=str(object_path),
        object_mask_ref=str(mask_path),
        width=40,
        height=40,
    )
    cfg = load_pipeline_config(
        "generate",
        overrides=[
            "flows/generate=generate_verify_v2",
            "patch_similarity.min_patch_side=8",
            "region_selection.scale_factors=[1.0]",
            "region_selection.fallback_scale_factors=[1.0]",
            "region_selection.iou_threshold=0.0",
            "region_selection.fallback_iou_threshold=0.0",
            "region_selection.stride_ratio=0.5",
        ],
    )
    variants = _build_object_variants(config=cfg, asset=asset)[:1]
    background = Image.new("RGB", (96, 96), (30, 30, 180))

    try:
        _find_best_patch(
            config=cfg,
            background_image=__import__("numpy").asarray(background),
            variants=variants,
            selected_boxes=[(0.0, 0.0, 96.0, 96.0)],
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert "selected_boxes=1" in message
    assert "primary:" in message


def test_generate_objects_uses_distinct_prompt_per_region(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seen_prompts: list[str] = []

    def fake_generate_region_objects(**kwargs):
        seen_prompts.append(kwargs["object_prompt"])
        return {
            region.region_id: GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=str(tmp_path / f"{region.region_id}.candidate.png"),
                object_ref=str(tmp_path / f"{region.region_id}.object.png"),
                object_mask_ref=str(tmp_path / f"{region.region_id}.mask.png"),
                width=32,
                height=32,
            )
            for region in kwargs["regions"]
        }

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_verify_v2.generate_region_objects",
        fake_generate_region_objects,
    )

    context = SimpleNamespace(
        object_generator_model=SimpleNamespace(
            load=lambda version: SimpleNamespace(model_id=version),
        ),
        model_versions=SimpleNamespace(object_generator="object-gen-v1"),
    )
    regions = [
        Region(
            region_id=f"r-{index}",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=32.0, h=32.0)),
            role=RegionRole.CANDIDATE,
            source=RegionSource.MANUAL,
            attributes={},
            version=1,
        )
        for index in range(1, 4)
    ]

    generated = _generate_objects(
        context=context,
        scene_dir=tmp_path,
        regions=regions,
        object_prompt="butterfly | antique brass key | crystal wine glass",
        object_negative_prompt="blurry",
        object_base_prompt="",
        object_base_negative_prompt="",
        object_generation_size=512,
    )

    assert list(generated) == ["r-1", "r-2", "r-3"]
    assert seen_prompts == ["butterfly | antique brass key | crystal wine glass"]


def test_generate_objects_uses_model_default_steps_and_guidance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seen_params: list[tuple[int, float]] = []

    class FakeObjectModel:
        default_num_inference_steps = 41
        default_guidance_scale = 7.25
        sampler = "dpmpp_sde_karras"

        def predict(self, handle, request):
            seen_params.append(
                (
                    int(request.params["num_inference_steps"]),
                    float(request.params["guidance_scale"]),
                )
            )
            Path(request.params["output_path"]).write_bytes(b"x")
            return {"output_path": request.params["output_path"]}

    class FakeMasker:
        def extract(self, *, image_path, output_prefix):
            object_path = Path(str(output_prefix)).with_suffix(".object.png")
            mask_path = Path(str(output_prefix)).with_suffix(".mask.png")
            raw_mask_path = Path(str(output_prefix)).with_suffix(".raw-mask.png")
            object_path.write_bytes(b"x")
            mask_path.write_bytes(b"x")
            raw_mask_path.write_bytes(b"x")
            return {
                "object": object_path,
                "mask": mask_path,
                "raw_alpha_mask": raw_mask_path,
                "mask_source": "stub",
                "alpha_bbox": "0,0,1,1",
                "alpha_nonzero_ratio": 1.0,
                "alpha_mean": 1.0,
                "alpha_has_signal": True,
            }

        def unload(self):
            return None

    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.objects.service.SamObjectMaskExtractor",
        lambda **kwargs: FakeMasker(),
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.objects.service.build_placement_assets",
        lambda **kwargs: SimpleNamespace(
            object_path=Path(kwargs["object_path"]),
            mask_path=Path(kwargs["mask_path"]),
            raw_alpha_path=Path(kwargs["raw_alpha_path"]),
            width=32,
            height=32,
            tight_bbox=(0, 0, 32, 32),
        ),
    )

    context = SimpleNamespace(
        runtime=SimpleNamespace(model_runtime=SimpleNamespace(device="cuda", dtype="float16", batch_size=1, seed=None)),
        object_generator_model=FakeObjectModel(),
    )
    regions = [
        Region(
            region_id="r-1",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=32.0, h=32.0)),
            role=RegionRole.CANDIDATE,
            source=RegionSource.MANUAL,
            attributes={},
            version=1,
        )
    ]

    generated = generate_region_objects(
        context=context,
        scene_dir=tmp_path,
        regions=regions,
        object_handle=SimpleNamespace(model_id="object-gen-v1"),
        object_prompt="butterfly",
        object_negative_prompt="blurry",
        object_generation_size=512,
    )

    assert list(generated) == ["r-1"]
    assert seen_params == [(41, 7.25)]


def test_mark_regions_as_answers_promotes_every_region() -> None:
    regions = [
        Region(
            region_id=f"r-{index}",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=32.0, h=32.0)),
            role=RegionRole.CANDIDATE,
            source=RegionSource.MANUAL,
            attributes={},
            version=1,
        )
        for index in range(1, 4)
    ]

    updated = _mark_regions_as_answers(regions)

    assert [region.role for region in updated] == [RegionRole.ANSWER] * 3
    assert [region.role for region in regions] == [RegionRole.CANDIDATE] * 3


def test_validate_generated_object_assets_rejects_missing_region(tmp_path: Path) -> None:
    regions = [
        Region(
            region_id="r-1",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=32.0, h=32.0)),
            role=RegionRole.ANSWER,
            source=RegionSource.MANUAL,
            attributes={},
            version=1,
        ),
        Region(
            region_id="r-2",
            geometry=Geometry(type="bbox", bbox=BBox(x=0.0, y=0.0, w=32.0, h=32.0)),
            role=RegionRole.ANSWER,
            source=RegionSource.MANUAL,
            attributes={},
            version=1,
        ),
    ]
    generated = {
        "r-1": GeneratedObjectAsset(
            region_id="r-1",
            candidate_ref=str(tmp_path / "r-1.candidate.png"),
            object_ref=str(tmp_path / "r-1.object.png"),
            object_mask_ref=str(tmp_path / "r-1.mask.png"),
            width=32,
            height=32,
        )
    }

    try:
        _validate_generated_object_assets(
            expected_regions=regions,
            generated_objects=generated,
            stage="pre_inpaint",
        )
    except RuntimeError as exc:
        assert "missing=['r-2']" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_validate_region_outputs_requires_every_region_record(tmp_path: Path) -> None:
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
    background = Background(
        asset_ref=str(tmp_path / "bg.png"),
        width=512,
        height=512,
        metadata={
            "inpaint_layer_candidates": [
                {"region_id": "r-1"},
                {"region_id": "r-2"},
            ]
        },
    )
    prompt_records = [
        RegionPromptRecord(
            region_id=f"r-{index}",
            prompt=f"object-{index}",
            negative_prompt="blur",
            generation_prompt=f"gen-{index}",
            bbox=(0.0, 0.0, 32.0, 32.0),
            composited_image_ref=str(tmp_path / f"r-{index}.composited.png"),
            selected_variant_ref=str(tmp_path / f"r-{index}.variant.png"),
        )
        for index in range(1, 4)
    ]

    try:
        _validate_region_outputs(
            background=background,
            regions=regions,
            region_prompt_records=prompt_records,
        )
    except RuntimeError as exc:
        assert "missing candidate payload region=r-3" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_build_background_skips_generator_and_upscaler_for_asset_ref_only(
    tmp_path: Path, monkeypatch
) -> None:
    background_source = tmp_path / "background.png"
    Image.new("RGBA", (32, 32), (255, 255, 255, 255)).save(background_source)
    load_calls: list[str] = []
    unload_calls: list[object] = []

    class _NeverLoadModel:
        def load(self, version):  # type: ignore[no-untyped-def]
            load_calls.append(str(version))
            raise AssertionError("model load should be skipped")

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_verify_v2.unload_model",
        lambda model: unload_calls.append(model),
    )

    context = SimpleNamespace(
        background_generator_model=_NeverLoadModel(),
        background_upscaler_model=_NeverLoadModel(),
        model_versions=SimpleNamespace(
            background_generator="bg-gen-v1", background_upscaler="bg-up-v1"
        ),
        runtime=SimpleNamespace(width=32, height=32),
    )

    background, prompt_record = _build_background(
        context=context,
        scene_dir=tmp_path / "scene",
        background_asset_ref=str(background_source),
        background_prompt=None,
        background_negative_prompt=None,
    )

    assert load_calls == []
    assert unload_calls == []
    assert prompt_record.mode == "asset_ref"
    assert background.asset_ref.endswith("background.png")
