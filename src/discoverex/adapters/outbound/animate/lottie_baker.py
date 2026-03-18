"""Lottie Baker — bake CSS keyframes into Lottie JSON as precomp wrapper.

No port interface — called directly by orchestrator (compositing.py pattern).
Source: wan_lottie_baker.py (split into baker + baker_transform for 200L).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .lottie_baker_transform import apply_keyframes_to_lottie

logger = logging.getLogger(__name__)


def bake_keyframes(
    lottie_path: str | Path,
    keyframe_data: dict,  # type: ignore[type-arg]
    output_path: str | Path,
) -> Path:
    """Bake keyframe transforms into Lottie JSON as precomp wrapper layer.

    Args:
        lottie_path: Source Lottie JSON (motion-only).
        keyframe_data: Keyframe dict with animation_type, keyframes, duration_ms, easing.
        output_path: Combined Lottie output path.

    Returns:
        Output file path.
    """
    with open(lottie_path, encoding="utf-8") as f:
        lottie = json.load(f)

    combined = apply_keyframes_to_lottie(lottie, keyframe_data)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(combined, f, separators=(",", ":"))

    size_mb = out.stat().st_size / (1024 * 1024)
    logger.info(f"[LottieBaker] combined: {out} ({size_mb:.1f}MB)")
    return out
