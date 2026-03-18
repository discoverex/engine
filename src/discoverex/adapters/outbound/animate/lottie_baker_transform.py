"""Lottie Baker transform — precomp wrapper keyframe injection."""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

EASING_MAP: dict[str, dict[str, list[float]]] = {
    "linear": {"x": [0.0, 1.0], "y": [0.0, 1.0]},
    "ease-in": {"x": [0.42, 1.0], "y": [0.0, 1.0]},
    "ease-out": {"x": [0.0, 0.58], "y": [1.0, 1.0]},
    "ease-in-out": {"x": [0.42, 0.58], "y": [0.0, 1.0]},
}


def apply_keyframes_to_lottie(lottie: dict[str, Any], kf_data: dict[str, Any]) -> dict[str, Any]:
    """Inject keyframes as precomp wrapper layer into Lottie structure."""
    result = copy.deepcopy(lottie)
    w = result.get("w", 480)
    h = result.get("h", 480)
    fps = result.get("fr", 16)
    total = result.get("op", 0) - result.get("ip", 0)

    if total <= 0:
        return result

    keyframes = kf_data.get("keyframes", [])
    if not keyframes:
        return result

    easing = EASING_MAP.get(kf_data.get("easing", "ease-in-out"), EASING_MAP["ease-in-out"])

    # Move existing layers to precomp asset
    precomp_id = "precomp_motion"
    precomp = {"id": precomp_id, "layers": result.get("layers", []), "fr": fps, "nm": "motion_layers"}
    result.setdefault("assets", []).append(precomp)

    # Build animated properties
    cx, cy = w / 2.0, h / 2.0
    pos, rot, scale, opacity = [], [], [], []

    for kf in keyframes:
        t = float(kf.get("t", 0))
        frame = round(t * total)
        tx, ty = float(kf.get("translateX", 0)), float(kf.get("translateY", 0))
        r = float(kf.get("rotate", 0))
        sx, sy = float(kf.get("scaleX", 1)), float(kf.get("scaleY", 1))
        op = float(kf.get("opacity", 1))

        ei = {"x": [easing["x"][0]], "y": [easing["y"][0]]}
        eo = {"x": [easing["x"][1]], "y": [easing["y"][1]]}

        pos.append({"t": frame, "s": [cx + tx, cy + ty, 0], "e": [cx + tx, cy + ty, 0], "i": ei, "o": eo})
        rot.append({"t": frame, "s": [r], "e": [r], "i": ei, "o": eo})
        scale.append({"t": frame, "s": [sx * 100, sy * 100, 100], "e": [sx * 100, sy * 100, 100], "i": ei, "o": eo})
        opacity.append({"t": frame, "s": [op * 100], "e": [op * 100], "i": ei, "o": eo})

    # Last keyframe = hold
    for kf_list in [pos, rot, scale, opacity]:
        if kf_list:
            last = kf_list[-1]
            last.pop("i", None)
            last.pop("o", None)
            last.pop("e", None)

    # Wrapper layer
    wrapper: dict[str, Any] = {
        "ddd": 0, "ind": 0, "ty": 0, "nm": "keyframe_wrapper",
        "refId": precomp_id, "sr": 1,
        "ks": {
            "o": {"a": 1, "k": opacity} if len(opacity) > 1 else {"a": 0, "k": 100},
            "r": {"a": 1, "k": rot} if len(rot) > 1 else {"a": 0, "k": 0},
            "p": {"a": 1, "k": pos} if len(pos) > 1 else {"a": 0, "k": [cx, cy, 0]},
            "a": {"a": 0, "k": [cx, cy, 0]},
            "s": {"a": 1, "k": scale} if len(scale) > 1 else {"a": 0, "k": [100, 100, 100]},
        },
        "ip": 0, "op": total, "st": 0, "bm": 0, "w": w, "h": h,
    }
    result["layers"] = [wrapper]
    return result
