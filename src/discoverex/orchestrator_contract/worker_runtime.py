from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from discoverex.config import PipelineConfig

from .artifacts import artifact_root_from_env, write_engine_artifact_manifest


def normalize_pipeline_config_for_worker_runtime(
    config: PipelineConfig,
) -> PipelineConfig:
    artifact_root = worker_artifact_root()
    if artifact_root is None:
        return config
    normalized = config.model_copy(deep=True)
    normalized.runtime.artifacts_root = str(artifact_root)
    return normalized


def worker_artifact_root() -> Path | None:
    try:
        return artifact_root_from_env()
    except RuntimeError:
        return None


def write_worker_artifact_manifest(
    *,
    artifacts_root: Path,
    artifacts: Sequence[tuple[str, Path | None]],
) -> Path | None:
    if worker_artifact_root() is None:
        return None
    entries: list[dict[str, str | None]] = []
    seen_paths: set[str] = set()
    for logical_name, artifact_path in artifacts:
        if artifact_path is None or not artifact_path.exists():
            continue
        resolved = artifact_path.resolve()
        try:
            relative = resolved.relative_to(artifacts_root.resolve())
        except ValueError:
            continue
        canonical = _canonicalize_artifact(
            artifacts_root=artifacts_root.resolve(),
            logical_name=logical_name,
            source_path=resolved,
            relative_path=relative,
        )
        relative_text = canonical["relative_path"]
        if relative_text in seen_paths:
            continue
        seen_paths.add(relative_text)
        entries.append(
            {
                "logical_name": canonical["logical_name"],
                "relative_path": relative_text,
                "content_type": _content_type_for_path(Path(canonical["absolute_path"])),
                "mlflow_tag": canonical["mlflow_tag"],
            }
        )
    return write_engine_artifact_manifest(entries)


def _content_type_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    return None


def _canonicalize_artifact(
    *,
    artifacts_root: Path,
    logical_name: str,
    source_path: Path,
    relative_path: Path,
) -> dict[str, str]:
    mapping = {
        "scene": ("scene_json", Path("scene/scene.json"), "artifact_scene_uri"),
        "verification": (
            "verification_json",
            Path("scene/verification.json"),
            "artifact_verification_uri",
        ),
        "naturalness": (
            "naturalness_json",
            Path("scene/naturalness.json"),
            "artifact_naturalness_uri",
        ),
    }
    target = mapping.get(logical_name)
    if target is None:
        return {
            "logical_name": logical_name,
            "relative_path": relative_path.as_posix(),
            "absolute_path": str(source_path),
            "mlflow_tag": "",
        }
    manifest_name, canonical_relative, mlflow_tag = target
    canonical_path = artifacts_root / canonical_relative
    if source_path.resolve() != canonical_path.resolve():
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, canonical_path)
    return {
        "logical_name": manifest_name,
        "relative_path": canonical_relative.as_posix(),
        "absolute_path": str(canonical_path),
        "mlflow_tag": mlflow_tag,
    }
