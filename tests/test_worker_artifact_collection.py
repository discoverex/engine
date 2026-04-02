from __future__ import annotations

from pathlib import Path

from discoverex.application.use_cases.worker_artifacts import (
    collect_worker_artifacts,
)


def test_collect_worker_artifacts_includes_nested_saved_dir_outputs(
    tmp_path: Path,
) -> None:
    saved_dir = tmp_path / "scenes" / "scene-1" / "version-1"
    metadata_dir = saved_dir / "metadata"
    nested_dir = saved_dir / "layers" / "objects"
    nested_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)

    scene_path = metadata_dir / "scene.json"
    verification_path = metadata_dir / "verification.json"
    composite_path = saved_dir / "composite.png"
    patch_path = nested_dir / "patch.png"
    mask_path = nested_dir / "mask.png"

    for path in [scene_path, verification_path, composite_path, patch_path, mask_path]:
        path.write_text("x", encoding="utf-8")

    artifacts = collect_worker_artifacts(
        saved_dir,
        [
            ("scene", scene_path),
            ("verification", verification_path),
            ("composite", composite_path),
        ],
    )

    artifact_map = {logical_name: path for logical_name, path in artifacts}

    assert artifact_map["scene"] == scene_path.resolve()
    assert artifact_map["verification"] == verification_path.resolve()
    assert artifact_map["composite"] == composite_path.resolve()
    assert artifact_map["bundle/layers/objects/patch.png"] == patch_path.resolve()
    assert artifact_map["bundle/layers/objects/mask.png"] == mask_path.resolve()
    assert len(artifacts) == 5
