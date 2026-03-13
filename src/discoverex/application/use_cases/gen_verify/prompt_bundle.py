from __future__ import annotations

import json
from pathlib import Path

from .types import PromptBundle

_PROMPT_PARAM_LIMIT = 250


def save_prompt_bundle(scene_dir: Path, prompt_bundle: PromptBundle) -> Path:
    path = scene_dir / "prompt_bundle.json"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                prompt_bundle.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
    return path


def build_prompt_tracking_params(prompt_bundle: PromptBundle) -> dict[str, str]:
    return {
        "input_mode": prompt_bundle.input_mode,
        "background_prompt_used": _truncate(prompt_bundle.background.prompt),
        "background_negative_prompt_used": _truncate(
            prompt_bundle.background.negative_prompt
        ),
        "object_prompt_used": _truncate(prompt_bundle.object.prompt),
        "object_negative_prompt_used": _truncate(prompt_bundle.object.negative_prompt),
        "final_prompt_used": _truncate(prompt_bundle.final_fx.prompt),
        "final_negative_prompt_used": _truncate(prompt_bundle.final_fx.negative_prompt),
    }


def _truncate(value: str, limit: int = _PROMPT_PARAM_LIMIT) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
