from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from discoverex.application.use_cases.gen_verify.types import RunIds

from .parse import sanitized_variant_id


def variant_run_ids(*, scene_id: str, variant_id: str) -> RunIds:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    safe_variant = sanitized_variant_id(variant_id)[:24]
    return RunIds(
        scene_id=scene_id,
        version_id=f"v-{stamp}-{safe_variant}",
        pipeline_run_id=f"run-{uuid4().hex[:12]}",
    )


def variant_prepare_dir(*, artifacts_root: Path, scene_id: str, prepare_id: str) -> Path:
    return artifacts_root / "experiments" / "inpaint_variant_pack" / scene_id / prepare_id


def reset_variant_background(background: Any) -> Any:
    cloned = background.model_copy(deep=True)
    cloned.metadata.pop("inpaint_composited_ref", None)
    cloned.metadata["inpaint_layer_candidates"] = []
    return cloned


def variant_args(base_args: dict[str, Any], *, variant_id: str) -> dict[str, Any]:
    args = dict(base_args)
    args.pop("variant_specs", None)
    args.pop("variant_specs_json", None)
    args["variant_id"] = variant_id
    return args
