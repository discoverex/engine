"""Lottie Baker transform — per-layer keyframe injection.

Applies keyframe transforms directly to each image layer (no precomp).
This avoids the precomp rendering overhead that causes frame drops when
many base64 PNG layers are composited at 60 fps.  Structure matches
test B (direct layer + fr=60) which was confirmed smoothest.
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
_KF_FPS = 60


def _cubic_bezier(t: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Solve CSS cubic-bezier via Newton's method."""
    u = t
    for _ in range(12):
        bx = 3 * x1 * u * (1 - u) ** 2 + 3 * x2 * u**2 * (1 - u) + u**3
        dbx = (
            3 * x1 * (1 - u) ** 2
            - 6 * x1 * u * (1 - u)
            + 6 * x2 * u * (1 - u)
            - 3 * x2 * u**2
            + 3 * u**2
        )
        if abs(dbx) < 1e-14:
            break
        u = max(0.0, min(1.0, u - (bx - t) / dbx))
    return 3 * y1 * u * (1 - u) ** 2 + 3 * y2 * u**2 * (1 - u) + u**3


def _eval_at(
    keyframes: list[dict[str, Any]],
    t_norm: float,
    bez: tuple[float, float, float, float],
    t_scale: float,
) -> dict[str, float]:
    """Evaluate the CSS keyframe animation at normalized time t ∈ [0,1]."""
    seg_s, seg_e = keyframes[0], keyframes[-1]
    for j in range(len(keyframes) - 1):
        if float(keyframes[j].get("t", 0)) <= t_norm <= float(keyframes[j + 1].get("t", 0)):
            seg_s, seg_e = keyframes[j], keyframes[j + 1]
            break
    ts, te = float(seg_s.get("t", 0)), float(seg_e.get("t", 0))
    local = (t_norm - ts) / (te - ts) if te != ts else 1.0
    eased = _cubic_bezier(local, *bez)
    defaults: dict[str, float] = {"scaleX": 1.0, "scaleY": 1.0, "opacity": 1.0}
    out: dict[str, float] = {}
    for p in ("translateX", "translateY", "rotate", "scaleX", "scaleY", "opacity"):
        d = defaults.get(p, 0.0)
        v0, v1 = float(seg_s.get(p, d)), float(seg_e.get(p, d))
        v = v0 + (v1 - v0) * eased
        out[p] = v * t_scale if p in ("translateX", "translateY") else v
    return out


def apply_keyframes_to_lottie(
    lottie: dict[str, Any], kf_data: dict[str, Any],
) -> dict[str, Any]:
    """Apply keyframe transforms directly to each image layer (no precomp)."""
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

    # MOTION_NEEDED: upsample fr to 60 with float ip/op
    elif result.get("fr", 16) < _KF_FPS:
        scale = _KF_FPS / result["fr"]
        new_total = round(total * scale)
        for layer in result.get("layers", []):
            layer["ip"] = layer.get("ip", 0) * scale
            layer["op"] = layer.get("op", 0) * scale
        result["fr"] = _KF_FPS
        result["ip"] = 0
        result["op"] = new_total
        total = new_total

    if total <= 0:
        return result
    keyframes = kf_data.get("keyframes", [])
    if not keyframes:
        return result

    # --- Scale + canvas expansion ---
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
    bez = _BEZIER.get(kf_data.get("easing", "ease-in-out"), _BEZIER["ease-in-out"])

    # --- Apply transforms to each layer directly (no precomp) ---
    # Each layer gets the transform values for its visibility window.
    # Linear bezier within the tiny window (~62.5 ms) is visually identical
    # to the global easing curve.  At any moment only 1 layer is active,
    # so rendering cost equals test-B (single image + fr=60).
    lin1: dict[str, Any] = {"x": [0.33], "y": [0.33]}
    lin3: dict[str, Any] = {"x": [0.33, 0.33, 0.33], "y": [0.33, 0.33, 0.33]}

    for layer in result.get("layers", []):
        lip = float(layer.get("ip", 0))
        lop = float(layer.get("op", 0))
        t0 = lip / total if total else 0
        t1 = lop / total if total else 0
        vs = _eval_at(keyframes, t0, bez, t_scale)
        ve = _eval_at(keyframes, t1, bez, t_scale)

        layer["ks"]["p"] = {"a": 1, "k": [
            {"t": lip, "s": [cx + vs["translateX"], cy + vs["translateY"], 0],
             "e": [cx + ve["translateX"], cy + ve["translateY"], 0],
             "o": lin3, "i": lin3},
            {"t": lop, "s": [cx + ve["translateX"], cy + ve["translateY"], 0]},
        ]}
        layer["ks"]["a"] = {"a": 0, "k": [anchor_x, anchor_y, 0]}
        layer["ks"]["r"] = {"a": 1, "k": [
            {"t": lip, "s": [vs["rotate"]], "e": [ve["rotate"]],
             "o": lin1, "i": lin1},
            {"t": lop, "s": [ve["rotate"]]},
        ]}
        layer["ks"]["s"] = {"a": 1, "k": [
            {"t": lip,
             "s": [vs["scaleX"] * 100, vs["scaleY"] * 100, 100],
             "e": [ve["scaleX"] * 100, ve["scaleY"] * 100, 100],
             "o": lin3, "i": lin3},
            {"t": lop, "s": [ve["scaleX"] * 100, ve["scaleY"] * 100, 100]},
        ]}
        layer["ks"]["o"] = {"a": 1, "k": [
            {"t": lip, "s": [vs["opacity"] * 100], "e": [ve["opacity"] * 100],
             "o": lin1, "i": lin1},
            {"t": lop, "s": [ve["opacity"] * 100]},
        ]}

    return result
