from __future__ import annotations

import colorsys
from math import sqrt

from PIL import Image


def masked_white_balance_error(image: Image.Image, mask: Image.Image) -> float:
    means = _masked_rgb_mean(image, mask)
    avg = sum(means) / 3.0
    return sqrt(sum((value - avg) ** 2 for value in means) / 3.0)


def masked_mean_saturation(image: Image.Image, mask: Image.Image) -> float:
    image_rgb = image.convert("RGB")
    mask_l = mask.convert("L")
    total = 0.0
    count = 0.0
    for y in range(image_rgb.height):
        for x in range(image_rgb.width):
            if mask_l.getpixel((x, y)) <= 0:
                continue
            r, g, b = image_rgb.getpixel((x, y))
            _, s, _ = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            total += float(s)
            count += 1.0
    if count <= 0:
        return 0.0
    return total / count


def masked_contrast(image: Image.Image, mask: Image.Image) -> float:
    gray = image.convert("L")
    mask_l = mask.convert("L")
    values: list[float] = []
    for y in range(gray.height):
        for x in range(gray.width):
            if mask_l.getpixel((x, y)) <= 0:
                continue
            values.append(float(gray.getpixel((x, y))))
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return sqrt(variance)


def _masked_rgb_mean(image: Image.Image, mask: Image.Image) -> tuple[float, float, float]:
    image_rgb = image.convert("RGB")
    mask_l = mask.convert("L")
    total = [0.0, 0.0, 0.0]
    count = 0.0
    for y in range(image_rgb.height):
        for x in range(image_rgb.width):
            if mask_l.getpixel((x, y)) <= 0:
                continue
            r, g, b = image_rgb.getpixel((x, y))
            total[0] += float(r)
            total[1] += float(g)
            total[2] += float(b)
            count += 1.0
    if count <= 0:
        return (0.0, 0.0, 0.0)
    return (total[0] / count, total[1] / count, total[2] / count)
