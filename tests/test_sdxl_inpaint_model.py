from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.adapters.outbound.models.sdxl_inpaint import SdxlInpaintModel
from discoverex.models.types import InpaintRequest


def test_sdxl_inpaint_writes_patch_and_composited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = SdxlInpaintModel(strict_runtime=True)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("inpaint-v1")
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), color="white").save(source)
    captured: dict[str, object] = {}

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        image = kwargs["image"]
        mask = kwargs["mask"]
        captured.update(kwargs)
        assert image.size == (128, 112)
        assert mask.size == (128, 112)
        generated = image.copy()
        ImageDraw.Draw(generated).ellipse((40, 24, 88, 80), fill=(20, 40, 220))
        return generated

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.has_meaningful_mask",
        lambda _mask: True,
    )
    output_path = tmp_path / "out.png"
    pred = model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r1",
            bbox=(10, 10, 20, 10),
            output_path=str(output_path),
            generation_prompt="hidden ruby",
        ),
    )

    assert pred["composited_image_ref"] == str(output_path)
    assert Path(pred["object_image_ref"]).exists()
    assert Path(pred["object_mask_ref"]).exists()
    assert output_path.exists()
    patch_path = Path(str(output_path).replace(".png", ".patch.png"))
    object_path = Path(str(output_path).replace(".png", ".object.png"))
    mask_path = Path(str(output_path).replace(".png", ".mask.png"))
    assert patch_path.exists()
    assert object_path.exists()
    assert mask_path.exists()
    assert Image.open(output_path).size == (64, 64)
    assert Image.open(patch_path).size == (128, 112)
    assert Image.open(object_path).size == (128, 112)
    assert Image.open(mask_path).size == (128, 112)
    composited = Image.open(output_path)
    assert composited.getpixel((5, 5)) == (255, 255, 255)
    assert composited.getpixel((20, 15)) != (255, 255, 255)
    assert captured["mask_blur"] == 4
    assert captured["inpaint_only_masked"] is True
    assert captured["padding_mask_crop"] == 32
    mask_bbox = Image.open(mask_path).getbbox()
    assert mask_bbox is not None
    assert mask_bbox[0] > 20
    assert mask_bbox[1] > 20
    assert mask_bbox[2] < 110
    assert mask_bbox[3] < 90


def test_sdxl_inpaint_normalizes_large_output_and_keeps_mask_local(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = SdxlInpaintModel(strict_runtime=True)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("inpaint-v1")
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), color=(240, 240, 240)).save(source)

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        image = kwargs["image"]
        generated = Image.new("RGB", (1024, 1024), color=(242, 242, 242))
        ImageDraw.Draw(generated).ellipse((420, 360, 620, 640), fill=(10, 20, 180))
        assert image.size == (128, 112)
        return generated

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.has_meaningful_mask",
        lambda _mask: True,
    )
    output_path = tmp_path / "out-large.png"
    pred = model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r2",
            bbox=(8, 12, 24, 12),
            output_path=str(output_path),
            generation_prompt="hidden blue gem",
        ),
    )

    mask = Image.open(pred["object_mask_ref"])
    assert mask.size == (128, 112)
    bbox = mask.getbbox()
    assert bbox is not None
    assert bbox[0] > 8
    assert bbox[1] > 20
    assert bbox[2] < 120
    assert bbox[3] < 92


def test_sdxl_inpaint_can_disable_masked_only_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = SdxlInpaintModel(
        strict_runtime=False,
        inpaint_only_masked=False,
        masked_area_padding=0,
        mask_blur=0,
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("inpaint-v1")
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 64), color="white").save(source)
    captured: dict[str, object] = {}

    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return kwargs["image"]

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)
    model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r3",
            bbox=(10, 10, 20, 10),
            output_path=str(tmp_path / "out-full-mask.png"),
            inpaint_only_masked=False,
            mask_blur=0,
            masked_area_padding=0,
        ),
    )

    assert captured["padding_mask_crop"] is None
    mask = captured["mask"]
    assert mask.getbbox() == (0, 0, 128, 64)


def test_resize_patch_to_long_side_uses_multiple_of_8() -> None:
    from discoverex.adapters.outbound.models.sdxl_inpaint_inference import (
        resize_patch_to_long_side,
    )

    patch = Image.new("RGB", (82, 77), color="white")
    resized, size = resize_patch_to_long_side(patch, 128)

    assert resized.size == size
    assert size == (128, 120)


def test_sdxl_inpaint_v2_selects_similarity_bbox_and_writes_precomposite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = SdxlInpaintModel(
        strict_runtime=True,
        inpaint_mode="similarity_overlay_v2",
        overlay_alpha=0.5,
        placement_grid_stride=8,
        placement_downscale_factor=1,
        final_inpaint_strength=0.18,
        final_inpaint_steps=6,
        final_inpaint_guidance_scale=2.0,
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("inpaint-v2")
    source = tmp_path / "source-v2.png"
    base = Image.new("RGB", (96, 96), color=(220, 220, 220))
    ImageDraw.Draw(base).rectangle((56, 24, 72, 40), fill=(32, 96, 196))
    base.save(source)
    candidate = tmp_path / "candidate.png"
    object_path = tmp_path / "object.png"
    mask_path = tmp_path / "mask.png"
    candidate_image = Image.new("RGB", (32, 32), color=(245, 245, 245))
    ImageDraw.Draw(candidate_image).rectangle((8, 8, 24, 24), fill=(32, 96, 196))
    candidate_image.save(candidate)
    object_image = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
    ImageDraw.Draw(object_image).rectangle((8, 8, 24, 24), fill=(32, 96, 196, 255))
    object_image.save(object_path)
    object_mask = Image.new("L", (32, 32), color=0)
    ImageDraw.Draw(object_mask).rectangle((8, 8, 24, 24), fill=255)
    object_mask.save(mask_path)
    captured: list[dict[str, object]] = []
    def _fake_generate_image(**kwargs):  # type: ignore[no-untyped-def]
        captured.append(dict(kwargs))
        return kwargs["image"].copy()

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)
    monkeypatch.setattr(
        model,
        "_find_similarity_placement",
        lambda **_kwargs: ((56, 24, 72, 40), 0.91),
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.has_meaningful_mask",
        lambda _mask: True,
    )
    pred = model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r-v2",
            bbox=(8, 8, 16, 16),
            object_candidate_ref=str(candidate),
            object_image_ref=str(object_path),
            object_mask_ref=str(mask_path),
            output_path=str(tmp_path / "out-v2.png"),
            generation_prompt="hidden marker",
        ),
    )

    assert Path(pred["candidate_image_ref"]) == candidate
    assert Path(pred["precomposited_image_ref"]).exists()
    assert Path(pred["blend_mask_ref"]).exists()
    assert pred["inpaint_mode"] == "similarity_overlay_v2"
    selected = pred["selected_bbox"]
    assert selected["x"] >= 48
    assert selected["y"] >= 16
    assert pred["placement_score"] >= 0.0
    assert len(captured) == 1
    assert captured[0]["inpaint_only_masked"] is True
    assert captured[0]["strength"] == pytest.approx(0.18)
    assert captured[0]["padding_mask_crop"] is None
    assert captured[0]["mask"].getbbox() is not None
    assert Image.open(pred["blend_mask_ref"]).getbbox() is not None


def test_layerdiffuse_hidden_object_mode_writes_stage_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = SdxlInpaintModel(
        strict_runtime=True,
        inpaint_mode="layerdiffuse_hidden_object_v1",
        relight_method="ic_light",
        edge_blend_backend="powerpaint_v2_sd15",
        core_blend_backend="powerpaint_v2_sd15",
        final_polish_backend="brushnet",
        mask_refine_backend="rmbg_2_0",
        rmbg_model_id="briaai/RMBG-2.0",
        ic_light_model_id="lllyasviel/ic-light",
        edge_blend_model_id="Sanster/PowerPaint_v2",
        core_blend_model_id="Sanster/PowerPaint_v2",
        final_polish_model_id="demo/brushnet",
        final_context_size=96,
        pre_match_variant_count=3,
        placement_grid_stride=8,
        placement_downscale_factor=1,
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.sdxl_inpaint.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("inpaint-hidden-object")
    source = tmp_path / "source-hidden.png"
    Image.new("RGB", (160, 160), color=(212, 214, 218)).save(source)
    candidate = tmp_path / "candidate-hidden.png"
    object_path = tmp_path / "object-hidden.png"
    mask_path = tmp_path / "mask-hidden.png"
    Image.new("RGBA", (80, 80), color=(0, 0, 0, 0)).save(candidate)
    object_image = Image.new("RGBA", (80, 80), color=(0, 0, 0, 0))
    ImageDraw.Draw(object_image).ellipse((16, 20, 60, 58), fill=(236, 208, 48, 255))
    object_image.save(object_path)
    object_mask = Image.new("L", (80, 80), color=0)
    ImageDraw.Draw(object_mask).ellipse((16, 20, 60, 58), fill=255)
    object_mask.save(mask_path)
    captured: list[dict[str, object]] = []

    class _FakeBackend:
        def __init__(self, label: str) -> None:
            self.label = label

        def generate(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.append({"label": self.label, **kwargs})
            return kwargs["image"].copy()

    monkeypatch.setattr(
        model,
        "_get_object_blend_backend",
        lambda kind: _FakeBackend(kind),
    )
    monkeypatch.setattr(
        model,
        "_refine_hidden_object_mask",
        lambda **kwargs: kwargs["fallback_mask"],
    )
    monkeypatch.setattr(
        model,
        "_apply_relight_hint",
        lambda image: image,
    )
    pred = model.predict(
        handle,
        InpaintRequest(
            image_ref=str(source),
            region_id="r-hidden",
            bbox=(20, 20, 32, 24),
            object_candidate_ref=str(candidate),
            object_image_ref=str(object_path),
            object_mask_ref=str(mask_path),
            output_path=str(tmp_path / "out-hidden.png"),
            negative_prompt="blurry",
        ),
    )

    assert pred["inpaint_mode"] == "layerdiffuse_hidden_object_v1"
    assert pred["placement_variant_id"].startswith("variant-")
    assert pred["mask_source"] == "rmbg_2_0"
    assert Path(pred["variant_manifest_ref"]).exists()
    assert Path(pred["precomposited_image_ref"]).exists()
    assert Path(pred["edge_mask_ref"]).exists()
    assert Path(pred["core_mask_ref"]).exists()
    assert Path(pred["edge_blend_ref"]).exists()
    assert Path(pred["core_blend_ref"]).exists()
    assert Path(pred["shadow_ref"]).exists()
    assert Path(pred["final_polish_ref"]).exists()
    assert len(captured) == 3
    assert captured[0]["label"] == "edge"
    assert captured[1]["label"] == "core"
    assert captured[2]["label"] == "final"
    assert captured[0]["strength"] == pytest.approx(0.18)
    assert captured[1]["strength"] == pytest.approx(0.35)
    assert captured[2]["strength"] == pytest.approx(0.12)
    assert captured[0]["mask"].getbbox() is not None
