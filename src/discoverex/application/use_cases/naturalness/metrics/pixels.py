from __future__ import annotations

from typing import cast

from PIL import Image


def rgb_pixel(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    return cast(tuple[int, int, int], image.getpixel((x, y)))


def gray_pixel(image: Image.Image, x: int, y: int) -> int:
    return int(cast(int, image.getpixel((x, y))))


def masked_rgb_mean(
    image: Image.Image, mask: Image.Image
) -> tuple[float, float, float]:
    image_rgb = image.convert("RGB")
    mask_l = mask.convert("L")
    total = [0.0, 0.0, 0.0]
    weight = 0.0
    for y in range(image_rgb.height):
        for x in range(image_rgb.width):
            r, g, b = rgb_pixel(image_rgb, x, y)
            alpha = gray_pixel(mask_l, x, y)
            if alpha <= 0:
                continue
            total[0] += float(r)
            total[1] += float(g)
            total[2] += float(b)
            weight += 1.0
    if weight <= 0.0:
        return (0.0, 0.0, 0.0)
    return (total[0] / weight, total[1] / weight, total[2] / weight)


def masked_gray_mean(image: Image.Image, mask: Image.Image) -> float:
    image_l = image.convert("L")
    mask_l = mask.convert("L")
    total = 0.0
    weight = 0.0
    for y in range(image_l.height):
        for x in range(image_l.width):
            alpha = gray_pixel(mask_l, x, y)
            if alpha <= 0:
                continue
            total += float(gray_pixel(image_l, x, y))
            weight += 1.0
    if weight <= 0.0:
        return 0.0
    return total / weight
