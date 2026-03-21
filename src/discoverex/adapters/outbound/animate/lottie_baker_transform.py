"""Lottie Baker transform — precomp wrapper keyframe injection."""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

# CSS cubic-bezier(x1, y1, x2, y2) for standard easing functions
_BEZIER: dict[str, tuple[float, float, float, float]] = {
    "linear": (0.0, 0.0, 1.0, 1.0),
    "ease": (0.25, 0.1, 0.25, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
}

_KF_FPS = 60  # match browser requestAnimationFrame


def _cubic_bezier(t: float, x1: float, y1: float, x2: float, y2: float) -> float:
    """Evaluate CSS cubic-bezier(x1,y1,x2,y2) at progress t ∈ [0,1].

    Solves B_x(u) = t for u via Newton's method, then returns B_y(u).
    Matches browser CSS animation-timing-function behavior exactly.
    """
    # Solve for u where B_x(u) = t
    u = t  # initial guess
    for _ in range(12):
        bx = 3 * x1 * u * (1 - u) ** 2 + 3 * x2 * u**2 * (1 - u) + u**3
        dbx = 3 * x1 * (1 - 3 * u + 2 * u**2) + 3 * x2 * (2 * u - 3 * u**2) + 3 * u**2 - 2 * u**3 + u**3
        # Correct derivative of cubic bezier x(u): d/du [3x1·u(1-u)² + 3x2·u²(1-u) + u³]
        dbx = 3 * x1 * (1 - u) ** 2 - 6 * x1 * u * (1 - u) + 6 * x2 * u * (1 - u) - 3 * x2 * u**2 + 3 * u**2
        if abs(dbx) < 1e-14:
            break
        u = u - (bx - t) / dbx
        u = max(0.0, min(1.0, u))
    # Evaluate B_y(u) with correct y1, y2 control points
    return 3 * y1 * u * (1 - u) ** 2 + 3 * y2 * u**2 * (1 - u) + u**3


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _resample_css(keyframes: list[dict[str, Any]], total: int, easing: str) -> list[dict[str, Any]]:
    """Resample sparse CSS keyframes to per-frame values, matching browser rendering."""
    if len(keyframes) < 2:
        return keyframes
    x1, y1, x2, y2 = _BEZIER.get(easing, _BEZIER["ease-in-out"])
    props = ("translateX", "translateY", "rotate", "scaleX", "scaleY", "opacity")
    defaults = {"scaleX": 1.0, "scaleY": 1.0, "opacity": 1.0}
    css_kfs = [(round(float(kf.get("t", 0)) * total), kf) for kf in keyframes]
    result = []
    for frame in range(total + 1):
        seg_s, seg_e = css_kfs[0], css_kfs[-1]
        for j in range(len(css_kfs) - 1):
            if css_kfs[j][0] <= frame <= css_kfs[j + 1][0]:
                seg_s, seg_e = css_kfs[j], css_kfs[j + 1]
                break
        sf, ef = seg_s[0], seg_e[0]
        local_t = (frame - sf) / (ef - sf) if ef != sf else 1.0
        eased = _cubic_bezier(local_t, x1, y1, x2, y2)
        vals: dict[str, Any] = {"t": frame}
        for p in props:
            d = defaults.get(p, 0.0)
            vals[p] = _lerp(float(seg_s[1].get(p, d)), float(seg_e[1].get(p, d)), eased)
        result.append(vals)
    return result


def _scale_translates(
    sampled: list[dict[str, Any]], w: int, h: int, ref_size: int,
) -> tuple[int, int]:
    """Scale CSS-pixel translate values to Lottie canvas units.

    Returns (canvas_w, canvas_h) — expanded to fit the scaled movement
    so the content doesn't clip.  When the Lottie is displayed at
    ``ref_size`` px, the movement matches the CSS animate() preview.
    """
    if ref_size <= 0 or min(w, h) <= ref_size:
        return w, h
    t_scale = min(w, h) / ref_size
    max_dx = max_dy = 0.0
    for s in sampled:
        s["translateX"] = s.get("translateX", 0.0) * t_scale
        s["translateY"] = s.get("translateY", 0.0) * t_scale
        max_dx = max(max_dx, abs(s["translateX"]))
        max_dy = max(max_dy, abs(s["translateY"]))
    if max_dx < 1 and max_dy < 1:
        return w, h
    pad_x = int(max_dx) + 1
    pad_y = int(max_dy) + 1
    return w + 2 * pad_x, h + 2 * pad_y


def apply_keyframes_to_lottie(lottie: dict[str, Any], kf_data: dict[str, Any]) -> dict[str, Any]:
    """Inject keyframes as precomp wrapper layer into Lottie structure."""
    result = copy.deepcopy(lottie)
    w = result.get("w", 480)
    h = result.get("h", 480)
    fps = result.get("fr", 16)
    total = result.get("op", 0) - result.get("ip", 0)

    # Single-frame Lottie (KEYFRAME_ONLY): expand timeline from duration_ms
    if total <= 1:
        dur_ms = kf_data.get("duration_ms", 1500)
        fps = _KF_FPS
        total = max(2, round(dur_ms / 1000 * fps))
        result["fr"] = fps
        result["ip"] = 0
        result["op"] = total
        for layer in result.get("layers", []):
            layer["op"] = total

    # Multi-frame Lottie (MOTION_NEEDED): upsample to _KF_FPS so keyframe
    # wrapper runs at 60 fps — matching the browser CSS animate() preview.
    # Motion frames are held proportionally (e.g. each 16-fps frame spans
    # ~3-4 frames at 60 fps), preserving the original playback duration.
    elif fps < _KF_FPS:
        scale = _KF_FPS / fps
        new_total = round(total * scale)
        for layer in result.get("layers", []):
            layer["ip"] = round(layer.get("ip", 0) * scale)
            layer["op"] = round(layer.get("op", 0) * scale)
        result["fr"] = _KF_FPS
        result["ip"] = 0
        result["op"] = new_total
        fps = _KF_FPS
        total = new_total

    if total <= 0:
        return result
    keyframes = kf_data.get("keyframes", [])
    if not keyframes:
        return result

    easing_name = kf_data.get("easing", "ease-in-out")
    precomp_id = "precomp_motion"
    precomp = {"id": precomp_id, "layers": result.get("layers", []), "fr": fps, "nm": "motion_layers"}
    result.setdefault("assets", []).append(precomp)

    # Resample CSS keyframes to per-frame (matches browser requestAnimationFrame)
    sampled = _resample_css(keyframes, total, easing_name)

    # Scale CSS-pixel translates to Lottie canvas units and expand canvas
    # so the proportional movement matches the browser CSS animate() preview.
    ref = kf_data.get("preview_object_size", 80)
    canvas_w, canvas_h = _scale_translates(sampled, w, h, ref)
    if canvas_w != w or canvas_h != h:
        result["w"] = canvas_w
        result["h"] = canvas_h

    # anchor = precomp content center, cx/cy = (expanded) canvas center
    anchor_x, anchor_y = w / 2.0, h / 2.0
    cx, cy = canvas_w / 2.0, canvas_h / 2.0

    pos, rot, scale, opacity = [], [], [], []
    for s in sampled:
        f = int(s["t"])
        pos.append({"t": f, "s": [cx + s["translateX"], cy + s["translateY"], 0]})
        rot.append({"t": f, "s": [s["rotate"]]})
        scale.append({"t": f, "s": [s["scaleX"] * 100, s["scaleY"] * 100, 100]})
        opacity.append({"t": f, "s": [s["opacity"] * 100]})

    for kf_list in [pos, rot, scale, opacity]:
        if len(kf_list) >= 2:
            for i in range(len(kf_list) - 1):
                kf_list[i]["e"] = kf_list[i + 1]["s"]

    wrapper: dict[str, Any] = {
        "ddd": 0, "ind": 0, "ty": 0, "nm": "keyframe_wrapper",
        "refId": precomp_id, "sr": 1,
        "ks": {
            "o": {"a": 1, "k": opacity} if len(opacity) > 1 else {"a": 0, "k": 100},
            "r": {"a": 1, "k": rot} if len(rot) > 1 else {"a": 0, "k": 0},
            "p": {"a": 1, "k": pos} if len(pos) > 1 else {"a": 0, "k": [cx, cy, 0]},
            "a": {"a": 0, "k": [anchor_x, anchor_y, 0]},
            "s": {"a": 1, "k": scale} if len(scale) > 1 else {"a": 0, "k": [100, 100, 100]},
        },
        "ip": 0, "op": total, "st": 0, "bm": 0, "w": w, "h": h,
    }
    result["layers"] = [wrapper]
    return result
