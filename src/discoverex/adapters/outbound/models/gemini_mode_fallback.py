"""Stage 3 fallback: keyword extraction with rigid-body detection.

Used when Gemini mode classifier returns unparseable JSON.
Ported from wan_mode_classifier.py `_extract_from_text()`.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── 보편적 강체 감지 패턴 (영문 + 중국어) ──
_NEGATIVE_PATTERNS = [
    "no joint", "no hinge", "no articulation", "no pivot",
    "no flexible", "no deformable", "no moving part",
    "does not bend", "does not flex", "does not deform",
    "cannot bend", "cannot flex",
    "rigid body", "rigid object", "single solid",
    "one solid piece", "fused together", "moves as one unit",
    "all parts are rigidly", "no visible joint",
    # 중국어 부정 표현 (Gemini가 중국어로 응답할 수 있음)
    "没有关节", "没有铰链", "不弯曲", "不变形",
    "刚性", "刚体", "一体", "整体移动",
]

_NO_DEFORM_EXPRESSIONS = [
    "answer no", "answer is no",
    "would not change shape", "would not deform",
    "outline shape would not", "shape does not change",
    "maintains its exact shape", "maintains its shape",
    "no part would bend", "no part would flex",
    "whole subject moves as one",
]

_ACTIONS = [
    "nudge_horizontal", "nudge_vertical", "wobble", "spin",
    "bounce", "pop", "launch", "float", "parabolic", "hop",
]


def extract_from_text(raw_lower: str) -> dict[str, Any]:
    """JSON 파싱 완전 실패 시 텍스트에서 키워드 추출. 보편적 강체 감지 포함."""
    mode = "motion_needed"  # safe fallback
    if "keyframe_only" in raw_lower:
        mode = "keyframe_only"

    # has_deformable_parts — 직접 키/값 검색
    has_def: bool | None = None
    if '"has_deformable_parts"' in raw_lower:
        after = raw_lower.split('"has_deformable_parts"')[1][:30]
        if "false" in after:
            has_def = False
        elif "true" in after:
            has_def = True

    # processing_mode 주변에서 교차 검증
    if '"processing_mode"' in raw_lower:
        after = raw_lower.split('"processing_mode"')[1][:40]
        if "keyframe_only" in after:
            mode = "keyframe_only"
            if has_def is None:
                has_def = False

    # ── 보편적 강체 감지 ──
    if has_def is None:
        rigid = any(p in raw_lower for p in _NEGATIVE_PATTERNS)
        no_ans = any(p in raw_lower for p in _NO_DEFORM_EXPRESSIONS)
        if rigid or no_ans:
            has_def = False
            mode = "keyframe_only"
            logger.info(
                f"[Stage1] rigid pattern detected: "
                f"rigid_reasoning={rigid} no_answer={no_ans} -> keyframe_only"
            )

    if has_def is None:
        has_def = True  # safe fallback

    # is_scene
    is_scene = False
    if '"is_scene"' in raw_lower:
        after = raw_lower.split('"is_scene"')[1][:20]
        if "true" in after:
            is_scene = True

    # facing_direction
    facing = "none"
    for d in ["left", "right", "up", "down"]:
        if f'"{d}"' in raw_lower:
            facing = d
            break

    # suggested_action
    action = ""
    for a in _ACTIONS:
        if f'"{a}"' in raw_lower:
            action = a
            break

    return {
        "processing_mode": mode,
        "has_deformable_parts": has_def,
        "is_scene": is_scene,
        "facing_direction": facing,
        "suggested_action": action,
        "subject_desc": "parsed from incomplete response",
        "reason": "JSON recovery fallback",
    }
