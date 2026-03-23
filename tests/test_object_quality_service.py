from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
from discoverex.application.use_cases.object_quality import evaluate_generated_objects


def test_evaluate_generated_objects_returns_three_scores(tmp_path: Path) -> None:
    assets: list[GeneratedObjectAsset] = []
    for index, color in enumerate(((255, 120, 80), (120, 200, 90), (90, 130, 255)), start=1):
        object_path = tmp_path / f"obj-{index}.png"
        mask_path = tmp_path / f"obj-{index}.mask.png"
        rgba = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
        draw = Image.new("RGBA", (20, 20), color=(*color, 255))
        rgba.paste(draw, (6, 6), draw)
        rgba.save(object_path)
        Image.new("L", (32, 32), color=0).save(mask_path)
        with Image.open(mask_path).convert("L") as mask:
            mask.paste(255, (6, 6, 26, 26))
            mask.save(mask_path)
        assets.append(
            GeneratedObjectAsset(
                region_id=f"r-{index}",
                candidate_ref=str(object_path),
                object_ref=str(object_path),
                object_mask_ref=str(mask_path),
                width=32,
                height=32,
                object_prompt=f"object-{index}",
            )
        )

    evaluation = evaluate_generated_objects(
        output_dir=tmp_path,
        object_prompt="butterfly | antique brass key | dinosaur",
        generated_objects=assets,
    )

    assert len(evaluation.scores) == 3
    assert evaluation.summary.object_count == 3
    assert evaluation.summary.run_score >= 0.0


def test_blur_metric_prefers_sharp_image(tmp_path: Path) -> None:
    sharp_path = tmp_path / "sharp.png"
    blur_path = tmp_path / "blur.png"
    mask_path = tmp_path / "mask.png"
    base = Image.new("RGBA", (32, 32), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    draw.rectangle((6, 6, 25, 25), fill=(200, 80, 60, 255))
    for offset in range(6, 26, 4):
        draw.line((6, offset, 25, offset), fill=(250, 220, 210, 255), width=1)
        draw.line((offset, 6, offset, 25), fill=(40, 20, 10, 255), width=1)
    base.save(sharp_path)
    base.filter(ImageFilter.GaussianBlur(radius=3)).save(blur_path)
    Image.new("L", (32, 32), color=0).save(mask_path)
    with Image.open(mask_path).convert("L") as mask:
        mask.paste(255, (6, 6, 26, 26))
        mask.save(mask_path)
    sharp_eval = evaluate_generated_objects(
        output_dir=tmp_path / "sharp",
        object_prompt="butterfly",
        generated_objects=[
            GeneratedObjectAsset(
                region_id="r-1",
                candidate_ref=str(sharp_path),
                object_ref=str(sharp_path),
                object_mask_ref=str(mask_path),
                width=32,
                height=32,
                object_prompt="butterfly",
            )
        ],
    )
    blur_eval = evaluate_generated_objects(
        output_dir=tmp_path / "blur",
        object_prompt="butterfly",
        generated_objects=[
            GeneratedObjectAsset(
                region_id="r-1",
                candidate_ref=str(blur_path),
                object_ref=str(blur_path),
                object_mask_ref=str(mask_path),
                width=32,
                height=32,
                object_prompt="butterfly",
            )
        ],
    )

    assert (
        sharp_eval.scores[0].metrics.laplacian_variance
        > blur_eval.scores[0].metrics.laplacian_variance
    )
