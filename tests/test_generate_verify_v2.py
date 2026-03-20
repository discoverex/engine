from __future__ import annotations

from pathlib import Path

from PIL import Image

from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
from discoverex.application.use_cases.generate_verify_v2 import (
    _build_object_variants,
    _bucket_patch_size,
    _find_best_patch,
    _harmonize_rgba,
)
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
