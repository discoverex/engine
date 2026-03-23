from __future__ import annotations

import csv
import shutil
from pathlib import Path

from .types import ObjectRenderSpec

_FRAME_COUNT = 60
_FPS = 60
_FRAME_TABLE_COLUMNS = [
    "frame",
    "object_id",
    "order",
    "x",
    "y",
    "w",
    "h",
    "rotation",
    "opacity",
    "src",
    "lottie_id",
]


def export_background(*, background_ref: str, background_dir: Path) -> Path:
    source = Path(background_ref)
    background_dir.mkdir(parents=True, exist_ok=True)
    target = background_dir / "background.png"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target


def export_object_images(
    *,
    specs: list[ObjectRenderSpec],
    objects_dir: Path,
) -> list[Path]:
    objects_dir.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    for spec in specs:
        source = Path(spec.source_ref)
        suffix = source.suffix or ".png"
        target = objects_dir / f"{spec.object_id}{suffix}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        exported.append(target)
    return exported


def write_frame_table(
    *,
    specs: list[ObjectRenderSpec],
    frame_table_path: Path,
) -> Path:
    frame_table_path.parent.mkdir(parents=True, exist_ok=True)
    with frame_table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FRAME_TABLE_COLUMNS)
        writer.writeheader()
        for frame in range(_FRAME_COUNT):
            for spec in specs:
                writer.writerow(
                    {
                        "frame": frame,
                        "object_id": spec.object_id,
                        "order": spec.order,
                        "x": spec.bbox["x"],
                        "y": spec.bbox["y"],
                        "w": spec.bbox["w"],
                        "h": spec.bbox["h"],
                        "rotation": 0,
                        "opacity": 1,
                        "src": f"{spec.object_id}.png",
                        "lottie_id": spec.lottie_id,
                    }
                )
    return frame_table_path


def frame_count() -> int:
    return _FRAME_COUNT


def frame_rate() -> int:
    return _FPS


def frame_table_columns() -> list[str]:
    return list(_FRAME_TABLE_COLUMNS)
