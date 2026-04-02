from __future__ import annotations

from math import log1p
from pathlib import Path

from PIL import Image, ImageDraw

from discoverex.application.use_cases.gen_verify.objects.prompts import split_object_prompts
from discoverex.application.use_cases.naturalness.metrics.color import (
    masked_contrast,
    masked_mean_saturation,
    masked_white_balance_error,
)
from discoverex.application.use_cases.naturalness.metrics.sharpness import (
    laplacian_variance,
)
from discoverex.domain.object_quality import (
    ObjectQualityEvaluation,
    ObjectQualityMetrics,
    ObjectQualityScore,
    ObjectQualitySubscores,
    ObjectQualitySummary,
)
from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset


def evaluate_generated_objects(
    *,
    output_dir: Path,
    object_prompt: str,
    generated_objects: list[GeneratedObjectAsset],
) -> ObjectQualityEvaluation:
    labels = _object_labels(object_prompt=object_prompt, count=len(generated_objects))
    scores: list[ObjectQualityScore] = []
    for index, (label, asset) in enumerate(zip(labels, generated_objects, strict=True), start=1):
        if not _can_evaluate(asset):
            continue
        evaluation_image_ref, metrics = _evaluate_asset(
            output_dir=output_dir,
            label=label,
            asset=asset,
            index=index,
        )
        subscores = _subscores(metrics)
        overall_score = _overall_score(subscores)
        scores.append(
            ObjectQualityScore(
                object_index=index,
                object_label=label,
                object_prompt=asset.object_prompt,
                object_ref=asset.object_ref,
                object_mask_ref=asset.object_mask_ref,
                raw_alpha_mask_ref=asset.raw_alpha_mask_ref,
                mask_source=asset.mask_source,
                metrics=metrics,
                subscores=subscores,
                overall_score=round(overall_score, 4),
                evaluation_image_ref=evaluation_image_ref,
            )
        )
    return ObjectQualityEvaluation(scores=scores, summary=_summary(scores))


def write_contact_sheet(
    *,
    output_dir: Path,
    evaluation: ObjectQualityEvaluation,
    combo_label: str,
    seed: int | None,
) -> Path:
    cards: list[Image.Image] = []
    for score in evaluation.scores:
        with Image.open(score.object_ref).convert("RGBA") as rgba:
            preview = rgba.copy()
        card = Image.new("RGB", (300, 380), color=(245, 245, 245))
        preview.thumbnail((260, 220))
        paste_left = (300 - preview.width) // 2
        card.paste((127, 127, 127), (20, 20, 280, 240))
        card.paste(preview, (paste_left, 20), preview)
        draw = ImageDraw.Draw(card)
        lines = [
            f"{score.object_index}. {score.object_label}",
            f"score={score.overall_score:.4f}",
            f"blur={score.metrics.laplacian_variance:.2f}",
            f"wb={score.metrics.white_balance_error:.2f}",
            f"sat={score.metrics.mean_saturation:.3f}",
            f"ctr={score.metrics.luma_stddev:.2f}",
        ]
        y = 255
        for line in lines:
            draw.text((18, y), line, fill=(20, 20, 20))
            y += 18
        cards.append(card)
    sheet_width = max(300, len(cards) * 300)
    sheet = Image.new("RGB", (sheet_width, 430), color=(255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    draw.text((16, 12), f"{combo_label} seed={seed if seed is not None else 'auto'}", fill=(0, 0, 0))
    for idx, card in enumerate(cards):
        sheet.paste(card, (idx * 300, 40))
    if not cards:
        draw.text((16, 64), "No evaluable object artifacts found.", fill=(80, 80, 80))
    output_path = output_dir / "quality.contact-sheet.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)
    return output_path


def _object_labels(*, object_prompt: str, count: int) -> list[str]:
    labels = split_object_prompts(object_prompt)
    if not labels:
        labels = [f"object-{index:02d}" for index in range(1, count + 1)]
    if len(labels) >= count:
        return labels[:count]
    return labels + [labels[-1]] * (count - len(labels))


def _evaluate_asset(
    *,
    output_dir: Path,
    label: str,
    asset: GeneratedObjectAsset,
    index: int,
) -> tuple[str, ObjectQualityMetrics]:
    eval_dir = output_dir / "quality"
    eval_dir.mkdir(parents=True, exist_ok=True)
    eval_path = eval_dir / f"{index:02d}.{label}.eval.png"
    with (
        Image.open(asset.object_ref).convert("RGBA") as rgba,
        Image.open(asset.object_mask_ref).convert("L") as mask,
    ):
        bbox = mask.getbbox() or (0, 0, mask.width, mask.height)
        rgba_crop = rgba.crop(bbox)
        mask_crop = mask.crop(bbox)
        canvas = Image.new("RGBA", rgba_crop.size, color=(127, 127, 127, 255))
        canvas.alpha_composite(rgba_crop)
        eval_rgb = canvas.convert("RGB")
        eval_rgb.save(eval_path)
        metrics = ObjectQualityMetrics(
            laplacian_variance=round(laplacian_variance(eval_rgb), 4),
            white_balance_error=round(masked_white_balance_error(rgba_crop, mask_crop), 4),
            mean_saturation=round(masked_mean_saturation(rgba_crop, mask_crop), 4),
            luma_stddev=round(masked_contrast(rgba_crop, mask_crop), 4),
        )
    return str(eval_path), metrics


def _subscores(metrics: ObjectQualityMetrics) -> ObjectQualitySubscores:
    return ObjectQualitySubscores(
        blur=round(_clamp01(log1p(max(0.0, metrics.laplacian_variance)) / 6.0), 4),
        white_balance=round(_clamp01(1.0 - metrics.white_balance_error / 64.0), 4),
        saturation=round(_clamp01(1.0 - abs(metrics.mean_saturation - 0.45) / 0.20), 4),
        contrast=round(_clamp01(metrics.luma_stddev / 64.0), 4),
    )


def _overall_score(subscores: ObjectQualitySubscores) -> float:
    weighted: list[tuple[float, float]] = [
        (0.40, subscores.blur),
        (0.20, subscores.white_balance),
        (0.20, subscores.saturation),
        (0.20, subscores.contrast),
    ]
    weight_sum = sum(weight for weight, _ in weighted)
    if weight_sum <= 0:
        return 0.0
    return sum(weight * value for weight, value in weighted) / weight_sum


def _summary(scores: list[ObjectQualityScore]) -> ObjectQualitySummary:
    if not scores:
        return ObjectQualitySummary()
    overall_values = [score.overall_score for score in scores]
    laplacian_values = [score.metrics.laplacian_variance for score in scores]
    wb_values = [score.metrics.white_balance_error for score in scores]
    sat_values = [score.metrics.mean_saturation for score in scores]
    contrast_values = [score.metrics.luma_stddev for score in scores]
    mean_overall = sum(overall_values) / len(overall_values)
    min_overall = min(overall_values)
    return ObjectQualitySummary(
        object_count=len(scores),
        mean_overall_score=round(mean_overall, 4),
        min_overall_score=round(min_overall, 4),
        min_laplacian_variance=round(min(laplacian_values), 4),
        mean_white_balance_error=round(sum(wb_values) / len(wb_values), 4),
        mean_saturation=round(sum(sat_values) / len(sat_values), 4),
        mean_contrast=round(sum(contrast_values) / len(contrast_values), 4),
        run_score=round(0.7 * mean_overall + 0.3 * min_overall, 4),
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _can_evaluate(asset: GeneratedObjectAsset) -> bool:
    return Path(asset.object_ref).is_file() and Path(asset.object_mask_ref).is_file()
