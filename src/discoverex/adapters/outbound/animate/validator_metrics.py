"""Validation metric calculation functions for animation quality checking."""

from __future__ import annotations

from typing import Any

import numpy as np

from .frame_extraction import get_bg_mask

# ---------------------------------------------------------------------------
# Motion metrics
# ---------------------------------------------------------------------------


def _calc_character_motion(frames: list[Any], bg_color: Any) -> float:
    if len(frames) < 2:
        return 0.0
    diffs = []
    for i in range(len(frames) - 1):
        bg1 = get_bg_mask(frames[i], bg_color)
        bg2 = get_bg_mask(frames[i + 1], bg_color)
        char_mask = ~(bg1 & bg2)
        if char_mask.sum() == 0:
            diffs.append(0.0)
            continue
        diffs.append(float(np.abs(frames[i + 1] - frames[i])[char_mask].mean()))
    return float(np.mean(diffs)) if diffs else 0.0


def _calc_raw_motion(frames: list[Any]) -> float:
    if len(frames) < 2:
        return 0.0
    d = [np.mean(np.abs(frames[i + 1] - frames[i])) for i in range(len(frames) - 1)]
    return float(np.mean(d))


def _calc_max_frame_diff(frames: list[Any]) -> float:
    if len(frames) < 2:
        return 0.0
    d = [np.mean(np.abs(frames[i + 1] - frames[i])) for i in range(len(frames) - 1)]
    return float(np.max(d))


def _count_motion_peaks(frames: list[Any]) -> int:
    if len(frames) < 4:
        return 0
    diffs = np.array([
        np.mean(np.abs(frames[i + 1] - frames[i])) for i in range(len(frames) - 1)
    ])
    threshold = np.mean(diffs) * 1.5
    return sum(
        1 for i in range(1, len(diffs) - 1)
        if diffs[i] > diffs[i - 1] and diffs[i] > diffs[i + 1] and diffs[i] > threshold
    )


# ---------------------------------------------------------------------------
# Spatial metrics
# ---------------------------------------------------------------------------


def _calc_edge_ratio(frames: list[Any], bg_color: Any) -> float:
    if not frames:
        return 0.0
    skip = 2
    safe = frames[skip:-skip] if len(frames) > skip * 2 + 2 else frames
    ratios = []
    for frame in safe[::2]:
        h, w, _ = frame.shape
        bs = max(5, h // 10)
        border = np.concatenate([
            frame[:bs, :, :].reshape(-1, 3), frame[-bs:, :, :].reshape(-1, 3),
            frame[:, :bs, :].reshape(-1, 3), frame[:, -bs:, :].reshape(-1, 3),
        ])
        non_bg = np.mean(np.any(np.abs(border - bg_color) > 0.25, axis=1))
        ratios.append(float(non_bg))
    return float(np.max(ratios))


def _calc_return_diff(frames: list[Any], bg_color: Any) -> float:
    if len(frames) < 2:
        return 0.0
    bg_f = get_bg_mask(frames[0], bg_color)
    bg_l = get_bg_mask(frames[-1], bg_color)
    mask = ~(bg_f & bg_l)
    if mask.sum() == 0:
        return 0.0
    return float(np.abs(frames[-1] - frames[0])[mask].mean())


def _calc_horizontal_drift(frames: list[Any], bg_color: Any) -> float:
    if len(frames) < 2:
        return 0.0
    _, w, _ = frames[0].shape
    cxs = []
    for f in frames:
        char = ~get_bg_mask(f, bg_color)
        if char.sum() == 0:
            continue
        _, xs = np.where(char)
        cxs.append(xs.mean() / w)
    if len(cxs) < 2:
        return 0.0
    ref = cxs[0]
    return float(np.max([abs(c - ref) for c in cxs[1:]]))


# ---------------------------------------------------------------------------
# Background / Ghost metrics
# ---------------------------------------------------------------------------


def _calc_bg_drift(frames: list[Any]) -> float:
    if len(frames) < 2:
        return 0.0

    def border_mean(frame: np.ndarray) -> Any:
        h, w = frame.shape[:2]
        bs = max(3, h // 20)
        pixels = np.concatenate([
            frame[:bs, :].reshape(-1, 3), frame[-bs:, :].reshape(-1, 3),
            frame[:, :bs].reshape(-1, 3), frame[:, -bs:].reshape(-1, 3),
        ])
        return pixels.mean(axis=0)

    ref = border_mean(frames[0])
    diffs = [float(np.abs(border_mean(f) - ref).mean()) for f in frames[1:]]
    return float(np.max(diffs)) if diffs else 0.0


def _calc_ghost_score(frames: list[Any], bg_color: Any) -> float:
    if len(frames) < 2:
        return 0.0
    bg_mask = get_bg_mask(frames[0], bg_color)
    if bg_mask.sum() < 100:
        return 0.0
    char_mask = ~bg_mask
    if char_mask.sum() == 0:
        return 0.0
    char_color = frames[0][char_mask].mean(axis=0)
    max_ghost = 0.0
    for frame in frames[1::2]:
        current_at_bg = frame[bg_mask]
        color_dist = np.abs(current_at_bg - char_color).mean(axis=1)
        ghost_ratio = float(np.mean(color_dist < (80 / 255.0)))
        if ghost_ratio > max_ghost:
            max_ghost = ghost_ratio
    return max_ghost


def _calc_char_brightness_drift(frames: list[Any], bg_color: Any) -> float:
    if len(frames) < 2:
        return 0.0
    ref_char = ~get_bg_mask(frames[0], bg_color)
    if ref_char.sum() == 0:
        return 0.0
    ref_bright = frames[0][ref_char].mean()
    drifts = []
    for frame in frames[1::3]:
        char = ~get_bg_mask(frame, bg_color)
        if char.sum() < 100:
            continue
        drifts.append(abs(float(frame[char].mean()) - float(ref_bright)))
    return float(np.max(drifts)) if drifts else 0.0
