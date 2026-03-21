from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
from discoverex.application.use_cases.generate_verify_v2 import (
    _build_object_variants,
    _bucket_patch_size,
    _crop_object_for_patch_selection,
    _find_best_patch,
    _generate_objects,
    _harmonize_rgba,
)
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.config_loader import load_pipeline_config


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
    selected_boxes = [(0.0, 0.0, 40.0, 40.0), (56.0, 0.0, 40.0, 40.0)]

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


def test_harmonize_rgba_preserves_alpha() -> None:
    rgba = Image.new("RGBA", (16, 16), (220, 50, 50, 200))
    patch = __import__("numpy").full((16, 16, 3), 120, dtype="uint8")
    harmonized = _harmonize_rgba(rgba=rgba, patch=patch, alpha=0.5)
    assert harmonized.mode == "RGBA"
    assert harmonized.getchannel("A").getextrema() == (200, 200)


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
        region = kwargs["regions"][0]
        return {
            region.region_id: GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=str(tmp_path / f"{region.region_id}.candidate.png"),
                object_ref=str(tmp_path / f"{region.region_id}.object.png"),
                object_mask_ref=str(tmp_path / f"{region.region_id}.mask.png"),
                width=32,
                height=32,
            )
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
        object_generation_size=512,
    )

    assert list(generated) == ["r-1", "r-2", "r-3"]
    assert seen_prompts == [
        "butterfly",
        "antique brass key",
        "crystal wine glass",
    ]
