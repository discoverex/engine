from __future__ import annotations

import shutil
from pathlib import Path

from .types import ObjectRenderSpec


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
