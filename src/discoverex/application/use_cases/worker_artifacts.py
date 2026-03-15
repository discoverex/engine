from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


def collect_worker_artifacts(
    saved_dir: Path,
    explicit_artifacts: Sequence[tuple[str, Path | None]],
) -> list[tuple[str, Path]]:
    collected: list[tuple[str, Path]] = []
    seen_paths: set[str] = set()

    for logical_name, artifact_path in explicit_artifacts:
        if artifact_path is None or not artifact_path.exists():
            continue
        resolved = artifact_path.resolve()
        key = str(resolved)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        collected.append((logical_name, resolved))

    if not saved_dir.exists():
        return collected

    saved_dir_resolved = saved_dir.resolve()
    for file_path in sorted(saved_dir_resolved.rglob("*")):
        if not file_path.is_file():
            continue
        resolved = file_path.resolve()
        key = str(resolved)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        relative = resolved.relative_to(saved_dir_resolved)
        collected.append((f"bundle/{relative.as_posix()}", resolved))
    return collected
