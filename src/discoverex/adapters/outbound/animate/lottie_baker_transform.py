"""Lottie Baker transform — precomp wrapper keyframe injection.

Uses Lottie-native bezier interpolation so the player renders smooth
keyframe animation at its own display rate.  No frame-by-frame
pre-computation — the sparse CSS keyframes are converted directly to
Lottie keyframes with ``o`` / ``i`` (out/in tangent) bezier easing.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

# CSS cubic-bezier(x1, y1, x2, y2) → Lottie out/in tangents
_BEZIER: dict[str, tuple[float, float, float, float]] = {
    "linear": (0.0, 0.0, 1.0, 1.0),
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
}

_KF_FPS = 60  # for KEYFRAME_ONLY timeline expansion


def apply_keyframes_to_lottie(
    lottie: dict[str, Any], kf_data: dict[str, Any],
) -> dict[str, Any]:
    """Inject keyframes as precomp wrapper with Lottie-native bezier easing."""
    result = copy.deepcopy(lottie)
    w = result.get("w", 480)
    h = result.get("h", 480)
    total = result.get("op", 0) - result.get("ip", 0)

    # KEYFRAME_ONLY: single-frame Lottie → expand timeline from duration_ms
    if total <= 1:
        dur_ms = kf_data.get("duration_ms", 1500)
        total = max(2, round(dur_ms / 1000 * _KF_FPS))
        result["fr"] = _KF_FPS
        result["ip"] = 0
        result["op"] = total
        for layer in result.get("layers", []):
            layer["op"] = total

    # MOTION_NEEDED: upsample fr to _KF_FPS so the Lottie player renders
    # at 60 fps (matching the browser's requestAnimationFrame).  Use exact
    # float ip/op so every original frame holds for *exactly* the same
    # duration — no round()-based 3/4 stutter.
    elif result.get("fr", 16) < _KF_FPS:
        orig_fps = result["fr"]
        scale = _KF_FPS / orig_fps  # e.g. 60/16 = 3.75
        new_total = round(total * scale)
        for layer in result.get("layers", []):
            layer["ip"] = layer.get("ip", 0) * scale  # float, not round
            layer["op"] = layer.get("op", 0) * scale  # float, not round
        result["fr"] = _KF_FPS
        result["ip"] = 0
        result["op"] = new_total
        total = new_total

    if total <= 0:
        return result
    keyframes = kf_data.get("keyframes", [])
    if not keyframes:
        return result

    # Move existing layers into precomp (no "fr" — not valid per Lottie spec)
    precomp_id = "precomp_motion"
    precomp: dict[str, Any] = {
        "id": precomp_id, "layers": result.get("layers", []), "nm": "motion_layers",
    }
    result.setdefault("assets", []).append(precomp)

    # --- Scale CSS-pixel translates to Lottie canvas units ---
    ref = kf_data.get("preview_object_size", 80)
    t_scale = min(w, h) / ref if ref > 0 and min(w, h) > ref else 1.0

    max_dx = max(abs(kf.get("translateX", 0.0)) * t_scale for kf in keyframes)
    max_dy = max(abs(kf.get("translateY", 0.0)) * t_scale for kf in keyframes)
    pad_x = int(max_dx) + 1 if max_dx >= 1 else 0
    pad_y = int(max_dy) + 1 if max_dy >= 1 else 0
    canvas_w, canvas_h = w + 2 * pad_x, h + 2 * pad_y
    if canvas_w != w or canvas_h != h:
        result["w"] = canvas_w
        result["h"] = canvas_h

    anchor_x, anchor_y = w / 2.0, h / 2.0
    cx, cy = canvas_w / 2.0, canvas_h / 2.0

    # --- Build Lottie keyframes with native bezier easing ---
    x1, y1, x2, y2 = _BEZIER.get(
        kf_data.get("easing", "ease-in-out"), _BEZIER["ease-in-out"],
    )
    bez_o1 = {"x": [x1], "y": [y1]}
    bez_i1 = {"x": [x2], "y": [y2]}
    bez_o3 = {"x": [x1, x1, x1], "y": [y1, y1, y1]}
    bez_i3 = {"x": [x2, x2, x2], "y": [y2, y2, y2]}

    pos, rot, scl, opa = _build_sparse_kfs(
        keyframes, total, t_scale, cx, cy, bez_o1, bez_i1, bez_o3, bez_i3,
    )

    wrapper: dict[str, Any] = {
        "ddd": 0, "ind": 0, "ty": 0, "nm": "keyframe_wrapper",
        "refId": precomp_id, "sr": 1,
        "ks": {
            "o": {"a": 1, "k": opa} if len(opa) > 1 else {"a": 0, "k": 100},
            "r": {"a": 1, "k": rot} if len(rot) > 1 else {"a": 0, "k": 0},
            "p": {"a": 1, "k": pos} if len(pos) > 1 else {"a": 0, "k": [cx, cy, 0]},
            "a": {"a": 0, "k": [anchor_x, anchor_y, 0]},
            "s": {"a": 1, "k": scl} if len(scl) > 1 else {"a": 0, "k": [100, 100, 100]},
        },
        "ip": 0, "op": total, "st": 0, "bm": 0, "w": w, "h": h,
    }
    result["layers"] = [wrapper]
    return result


def _build_sparse_kfs(
    keyframes: list[dict[str, Any]],
    total: int,
    t_scale: float,
    cx: float,
    cy: float,
    bez_o1: dict[str, list[float]],
    bez_i1: dict[str, list[float]],
    bez_o3: dict[str, list[float]],
    bez_i3: dict[str, list[float]],
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Convert sparse CSS keyframes to Lottie keyframes with bezier."""
    pos: list[Any] = []
    rot: list[Any] = []
    scl: list[Any] = []
    opa: list[Any] = []

    for idx, kf in enumerate(keyframes):
        t = round(float(kf.get("t", 0)) * total)
        tx = kf.get("translateX", 0.0) * t_scale
        ty = kf.get("translateY", 0.0) * t_scale

        p: dict[str, Any] = {"t": t, "s": [cx + tx, cy + ty, 0]}
        r: dict[str, Any] = {"t": t, "s": [kf.get("rotate", 0.0)]}
        s: dict[str, Any] = {
            "t": t,
            "s": [kf.get("scaleX", 1.0) * 100, kf.get("scaleY", 1.0) * 100, 100],
        }
        o: dict[str, Any] = {"t": t, "s": [kf.get("opacity", 1.0) * 100]}

        if idx < len(keyframes) - 1:
            nk = keyframes[idx + 1]
            ntx = nk.get("translateX", 0.0) * t_scale
            nty = nk.get("translateY", 0.0) * t_scale
            p["e"] = [cx + ntx, cy + nty, 0]
            p["o"] = bez_o3
            p["i"] = bez_i3
            r["e"] = [nk.get("rotate", 0.0)]
            r["o"] = bez_o1
            r["i"] = bez_i1
            s["e"] = [nk.get("scaleX", 1.0) * 100, nk.get("scaleY", 1.0) * 100, 100]
            s["o"] = bez_o3
            s["i"] = bez_i3
            o["e"] = [nk.get("opacity", 1.0) * 100]
            o["o"] = bez_o1
            o["i"] = bez_i1

        pos.append(p)
        rot.append(r)
        scl.append(s)
        opa.append(o)

    return pos, rot, scl, opa
