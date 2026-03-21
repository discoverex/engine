from __future__ import annotations

import shutil
import json
from pathlib import Path

from .types import CandidateLayerPayload, OriginalAssetEntry


def export_originals(
    *,
    originals_dir: Path,
    candidates: dict[str, CandidateLayerPayload],
) -> tuple[list[Path], list[OriginalAssetEntry]]:
    exported: list[Path] = []
    manifest: list[OriginalAssetEntry] = []
    for region_id, candidate in sorted(candidates.items()):
        region_dir = originals_dir / region_id
        region_dir.mkdir(parents=True, exist_ok=True)
        for key in (
            "candidate_image_ref",
            "generated_object_image_ref",
            "generated_object_mask_ref",
            "generated_raw_alpha_mask_ref",
            "object_image_ref",
            "processed_object_image_ref",
            "processed_object_mask_ref",
            "object_mask_ref",
            "raw_alpha_mask_ref",
            "patch_image_ref",
            "selected_variant_ref",
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
                    "path": f"original/{region_id}/{target.name}",
                }
            )
        diagnostics = {
            key: candidate.get(key)
            for key in (
                "region_id",
                "bbox",
                "object_prompt_resolved",
                "object_negative_prompt_resolved",
                "generation_prompt_resolved",
                "object_model_id",
                "object_sampler",
                "object_steps",
                "object_guidance_scale",
                "object_seed",
                "mask_source",
                "alpha_has_signal",
                "alpha_bbox",
                "alpha_nonzero_ratio",
                "alpha_mean",
                "selected_variant_ref",
            )
            if candidate.get(key) is not None
        }
        diagnostics_path = region_dir / "diagnostics.json"
        diagnostics_path.write_text(
            json.dumps(diagnostics, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        exported.append(diagnostics_path)
        manifest.append(
            {
                "region_id": region_id,
                "kind": "diagnostics",
                "path": f"original/{region_id}/{diagnostics_path.name}",
            }
        )
    return exported, manifest
