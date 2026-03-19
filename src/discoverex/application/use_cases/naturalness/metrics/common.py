from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from discoverex.domain.naturalness import SelectedBBox


def sanitize_bbox(
    bbox: SelectedBBox, width: int, height: int
) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(round(float(bbox["x"])))))
    y1 = max(0, min(height - 1, int(round(float(bbox["y"])))))
    x2 = max(x1 + 1, min(width, int(round(float(bbox["x"]) + float(bbox["w"])))))
    y2 = max(y1 + 1, min(height, int(round(float(bbox["y"]) + float(bbox["h"])))))
    return (x1, y1, x2, y2)


def average(values: Iterable[float]) -> float:
    items = list(values)
    return round(sum(items) / len(items), 4) if items else 0.0


def clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(float(value), 1.0))


def as_str(value: object) -> str | None:
    return str(value) if isinstance(value, (str, Path)) and str(value) else None


def as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
