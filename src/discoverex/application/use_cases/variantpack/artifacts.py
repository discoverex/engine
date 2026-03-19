from __future__ import annotations

from pathlib import Path
from typing import Any

from discoverex.artifact_paths import (
    naturalness_json_path,
    output_manifest_path,
    prompt_bundle_json_path,
    scene_json_path,
    verification_json_path,
)

from .runtime import variant_prepare_dir


def variant_manifest_path(*, artifacts_root: Path, scene_id: str, prepare_id: str) -> Path:
    path = variant_prepare_dir(
        artifacts_root=artifacts_root,
        scene_id=scene_id,
        prepare_id=prepare_id,
    )
    path.mkdir(parents=True, exist_ok=True)
    return path / "variant_pack.json"


def variant_artifact_entries(
    *,
    artifacts_root: Path,
    variant_result: dict[str, Any],
) -> list[tuple[str, Path | None]]:
    scene_id = str(variant_result.get("scene_id", "")).strip()
    version_id = str(variant_result.get("version_id", "")).strip()
    variant_id = str(variant_result.get("variant_id", "")).strip() or "variant"
    if not scene_id or not version_id:
        return []
    output_dir = artifacts_root / "scenes" / scene_id / version_id / "outputs"
    return [
        (f"variant/{variant_id}/scene", scene_json_path(artifacts_root, scene_id, version_id)),
        (
            f"variant/{variant_id}/verification",
            verification_json_path(artifacts_root, scene_id, version_id),
        ),
        (
            f"variant/{variant_id}/naturalness",
            naturalness_json_path(artifacts_root, scene_id, version_id),
        ),
        (
            f"variant/{variant_id}/prompt_bundle",
            prompt_bundle_json_path(artifacts_root, scene_id, version_id),
        ),
        (
            f"variant/{variant_id}/output_manifest",
            output_manifest_path(artifacts_root, scene_id, version_id),
        ),
        (f"variant/{variant_id}/lottie", output_dir / "animation.lottie"),
    ]


def variant_manifest_payload(
    *,
    scene_id: str,
    prepare_dir: Path,
    prepare_pipeline_run_id: str,
    variant_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "scene_id": scene_id,
        "prepare_pipeline_run_id": prepare_pipeline_run_id,
        "prepare_dir": str(prepare_dir),
        "variant_count": len(variant_results),
        "variants": variant_results,
    }
