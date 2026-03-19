from __future__ import annotations

from pathlib import Path


def scene_root(artifacts_root: Path | str, scene_id: str, version_id: str) -> Path:
    return Path(artifacts_root) / "scenes" / scene_id / version_id


def metadata_dir(artifacts_root: Path | str, scene_id: str, version_id: str) -> Path:
    return scene_root(artifacts_root, scene_id, version_id) / "metadata"


def outputs_dir(artifacts_root: Path | str, scene_id: str, version_id: str) -> Path:
    return scene_root(artifacts_root, scene_id, version_id) / "outputs"


def assets_dir(artifacts_root: Path | str, scene_id: str, version_id: str) -> Path:
    return scene_root(artifacts_root, scene_id, version_id) / "assets"


def debug_dir(artifacts_root: Path | str, scene_id: str, version_id: str) -> Path:
    return scene_root(artifacts_root, scene_id, version_id) / "debug"


def scene_json_path(artifacts_root: Path | str, scene_id: str, version_id: str) -> Path:
    return metadata_dir(artifacts_root, scene_id, version_id) / "scene.json"


def verification_json_path(
    artifacts_root: Path | str, scene_id: str, version_id: str
) -> Path:
    return metadata_dir(artifacts_root, scene_id, version_id) / "verification.json"


def naturalness_json_path(
    artifacts_root: Path | str, scene_id: str, version_id: str
) -> Path:
    return metadata_dir(artifacts_root, scene_id, version_id) / "naturalness.json"


def prompt_bundle_json_path(
    artifacts_root: Path | str, scene_id: str, version_id: str
) -> Path:
    return metadata_dir(artifacts_root, scene_id, version_id) / "prompt_bundle.json"


def output_manifest_path(
    artifacts_root: Path | str, scene_id: str, version_id: str
) -> Path:
    return outputs_dir(artifacts_root, scene_id, version_id) / "manifest.json"


def composite_output_path(
    artifacts_root: Path | str, scene_id: str, version_id: str
) -> Path:
    return outputs_dir(artifacts_root, scene_id, version_id) / "composite.png"
