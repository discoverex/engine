"""AnimationValidationPort implementation — numerical quality validation.

Validates WAN I2V output against 8 quality metrics:
  1. no_motion           2. too_slow          3. too_fast
  4. repeated_motion     5. frame_escape      6. no_return_to_origin
  7. center_drift        8. ghosting / background_color_change

Dependencies: PIL, numpy, ffmpeg (subprocess).
"""

from __future__ import annotations

import logging
from pathlib import Path

from discoverex.domain.animate import (
    AnimationValidation,
    AnimationValidationThresholds,
    VisionAnalysis,
)

from .frame_extraction import detect_bg_color, extract_frames
from .validator_metrics import (
    _calc_bg_drift,
    _calc_char_brightness_drift,
    _calc_character_motion,
    _calc_edge_ratio,
    _calc_ghost_score,
    _calc_horizontal_drift,
    _calc_max_frame_diff,
    _calc_raw_motion,
    _calc_return_diff,
    _count_motion_peaks,
)

logger = logging.getLogger(__name__)

BG_DRIFT_THRESHOLD = 30 / 255.0
GHOST_THRESHOLD = 0.005


class NumericalAnimationValidator:
    """Validate animation video against numerical quality thresholds."""

    def validate(
        self,
        video: Path,
        original_analysis: VisionAnalysis,
        thresholds: AnimationValidationThresholds,
    ) -> AnimationValidation:
        min_motion = original_analysis.min_motion
        max_motion = original_analysis.max_motion
        max_diff = original_analysis.max_diff

        frames = extract_frames(str(video))
        if not frames:
            return AnimationValidation(
                passed=False, failed_checks=["frame_extraction_failed"],
            )

        bg_color = detect_bg_color(frames[0])
        failed: list[str] = []
        scores: dict[str, float] = {}

        char_motion = _calc_character_motion(frames, bg_color)
        raw_motion = _calc_raw_motion(frames)
        scores["motion"] = round(char_motion, 4)
        scores["raw_motion"] = round(raw_motion, 4)

        # 1. no_motion
        if char_motion < min_motion * 0.5:
            failed.append("no_motion")

        # 2. too_slow
        if char_motion < min_motion:
            failed.append("too_slow")

        # 3. too_fast
        max_diff_score = _calc_max_frame_diff(frames)
        scores["max_diff"] = round(max_diff_score, 4)
        raw_too_fast = raw_motion > (min_motion * 0.5)
        if (char_motion > max_motion and raw_too_fast) or max_diff_score > max_diff:
            failed.append("too_fast")

        # 4. repeated_motion
        peaks = _count_motion_peaks(frames)
        scores["peaks"] = float(peaks)
        if peaks > thresholds.max_repeat_peaks:
            failed.append("repeated_motion")

        # 5. frame_escape (suppressed when bg_drift is high)
        bg_drift = _calc_bg_drift(frames)
        scores["bg_drift"] = round(bg_drift * 255)
        edge_ratio = _calc_edge_ratio(frames, bg_color)
        scores["edge_ratio"] = round(edge_ratio, 4)
        if edge_ratio > thresholds.max_edge_ratio and bg_drift <= BG_DRIFT_THRESHOLD:
            failed.append("frame_escape")

        # 6. no_return_to_origin
        return_diff = _calc_return_diff(frames, bg_color)
        scores["return_diff"] = round(return_diff, 4)
        if return_diff > thresholds.max_return_diff:
            failed.append("no_return_to_origin")

        # 7. center_drift
        drift = _calc_horizontal_drift(frames, bg_color)
        scores["center_drift"] = round(drift, 4)
        if drift > thresholds.max_center_drift:
            failed.append("center_drift")

        # 8. ghosting + background_color_change
        ghost = _calc_ghost_score(frames, bg_color)
        scores["ghost_score"] = round(ghost, 4)
        if ghost > GHOST_THRESHOLD:
            failed.append("ghosting")

        if bg_drift > BG_DRIFT_THRESHOLD:
            char_bright = _calc_char_brightness_drift(frames, bg_color)
            scores["char_brightness_drift"] = round(char_bright * 255)
            if char_bright > BG_DRIFT_THRESHOLD:
                failed.append("background_color_change")

        return AnimationValidation(
            passed=len(failed) == 0, failed_checks=failed, scores=scores,
        )
