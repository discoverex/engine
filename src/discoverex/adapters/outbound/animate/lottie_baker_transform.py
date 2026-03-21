"""Lottie Baker transform — null-parent keyframe injection.

Creates an invisible null layer (ty=3) with the animated keyframe
transforms, and parents all image layers to it.  This gives the
smoothness of a single animated element (test B) while keeping the
64 image layers static (test F).
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

_BEZIER: dict[str, tuple[float, float, float, float]] = {
    "linear": (0.0, 0.0, 1.0, 1.0),
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
}
_KF_FPS = 48  # 16×3 — integer multiple avoids 3/4 stutter at any viewer


def apply_keyframes_to_lottie(
    lottie: dict[str, Any], kf_data: dict[str, Any],
) -> dict[str, Any]:
    """Inject keyframes via null parent layer — no precomp, no per-layer anim."""
    result = copy.deepcopy(lottie)
    w = result.get("w", 480)
    h = result.get("h", 480)
    total = result.get("op", 0) - result.get("ip", 0)

    # KEYFRAME_ONLY: expand single-frame timeline
    if total <= 1:
        dur_ms = kf_data.get("duration_ms", 1500)
        total = max(2, round(dur_ms / 1000 * _KF_FPS))
        result["fr"] = _KF_FPS
        result["ip"] = 0
        result["op"] = total
        for layer in result.get("layers", []):
            layer["op"] = total

    # MOTION_NEEDED: upsample to _KF_FPS (48 = 16×3).
    # Integer multiple of original fr ensures every frame holds for exactly
    # the same number of composition frames (3), avoiding 3/4 stutter.
    # 48 fps is smooth without setSubframe and lighter than 60 fps.
    elif result.get("fr", 16) < _KF_FPS:
        orig_fr = result["fr"]
        # Use nearest integer multiple of orig_fr that's >= _KF_FPS
        mult = max(1, round(_KF_FPS / orig_fr))
        target_fr = orig_fr * mult
        new_total = total * mult
        for layer in result.get("layers", []):
            layer["ip"] = layer.get("ip", 0) * mult
            layer["op"] = layer.get("op", 0) * mult
        result["fr"] = target_fr
        result["ip"] = 0
        result["op"] = new_total
        total = new_total

    if total <= 0:
        return result
    keyframes = kf_data.get("keyframes", [])
    if not keyframes:
        return result

    cx, cy = w / 2.0, h / 2.0
    result_fr = result.get("fr", 16)

    # Keyframe duration in frames — matches CSS animate() duration_ms,
    # NOT the full motion length.  After kf_frames the null holds its
    # last value (= rest position), so the motion continues without transform.
    dur_ms = kf_data.get("duration_ms") or round(total / result_fr * 1000)
    kf_frames = min(total, round(dur_ms / 1000 * result_fr))

    # No translate scaling — use CSS pixel values directly.
    # The preview's CSS translate(Xpx) operates in the same space as the
    # Lottie canvas, keeping movement proportional and within bounds.
    lin1: dict[str, Any] = {"x": [0], "y": [0]}
    lni1: dict[str, Any] = {"x": [1], "y": [1]}
    lin3: dict[str, Any] = {"x": [0, 0, 0], "y": [0, 0, 0]}
    lni3: dict[str, Any] = {"x": [1, 1, 1], "y": [1, 1, 1]}

    pos, rot, scl, opa = _build_sparse_kfs(
        keyframes, kf_frames, 1.0, cx, cy, lin1, lni1, lin3, lni3,
    )

    null_ind = 9999
    null_layer: dict[str, Any] = {
        "ddd": 0, "ind": null_ind, "ty": 3, "nm": "keyframe_ctrl",
        "sr": 1,
        "ks": {
            "o": {"a": 1, "k": opa} if len(opa) > 1 else {"a": 0, "k": 100},
            "r": {"a": 1, "k": rot} if len(rot) > 1 else {"a": 0, "k": 0},
            "p": {"a": 1, "k": pos} if len(pos) > 1 else {"a": 0, "k": [cx, cy, 0]},
            "a": {"a": 0, "k": [cx, cy, 0]},
            "s": {"a": 1, "k": scl} if len(scl) > 1 else {"a": 0, "k": [100, 100, 100]},
        },
        "ip": 0, "op": total, "st": 0,
    }

    # Parent all image layers to the null — they keep static transforms
    for layer in result.get("layers", []):
        layer["parent"] = null_ind

    result["layers"].insert(0, null_layer)
    return result


def _build_sparse_kfs(
    keyframes: list[dict[str, Any]],
    total: int,
    t_scale: float,
    cx: float,
    cy: float,
    bez_o1: dict[str, Any],
    bez_i1: dict[str, Any],
    bez_o3: dict[str, Any],
    bez_i3: dict[str, Any],
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
