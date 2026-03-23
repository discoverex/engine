from __future__ import annotations

from pathlib import Path


def resolve_artifact_path(artifact_dir: Path, relative_path: str) -> Path:
    resolved = (artifact_dir / relative_path).resolve()
    try:
        resolved.relative_to(artifact_dir.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"engine artifact escapes artifact root: {relative_path}"
        ) from exc
    if not resolved.exists() or not resolved.is_file():
        raise RuntimeError(f"engine artifact file not found: {relative_path}")
    return resolved
