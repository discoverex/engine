from __future__ import annotations

import shutil
from pathlib import Path

from .types import CandidateLayerPayload, IntermediateAssetEntry


def export_intermediates(
    *,
    intermediates_dir: Path,
    candidates: dict[str, CandidateLayerPayload],
) -> tuple[list[Path], list[IntermediateAssetEntry]]:
    exported: list[Path] = []
    manifest: list[IntermediateAssetEntry] = []
    for region_id, candidate in sorted(candidates.items()):
        region_dir = intermediates_dir / region_id
        region_dir.mkdir(parents=True, exist_ok=True)
        for key in (
            "candidate_image_ref",
            "object_image_ref",
            "object_mask_ref",
            "raw_alpha_mask_ref",
            "patch_image_ref",
            "precomposited_image_ref",
            "blend_mask_ref",
            "edge_mask_ref",
            "core_mask_ref",
            "shadow_ref",
            "edge_blend_ref",
            "core_blend_ref",
            "final_polish_ref",
            "variant_manifest_ref",
        ):
            value = candidate.get(key)
            if not isinstance(value, str) or not value:
                continue
            source = Path(value)
            if not source.exists() or not source.is_file():
                continue
            target = region_dir / source.name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            exported.append(target)
            manifest.append(
                {
                    "region_id": region_id,
                    "kind": key,
                    "path": f"intermediates/{region_id}/{target.name}",
                }
            )
    return exported, manifest
