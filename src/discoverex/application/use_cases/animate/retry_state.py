"""Retry loop state and constants for animate generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discoverex.domain.animate import VisionAnalysis

ISSUE_NEGATIVE_MAP: dict[str, str] = {
    "ghosting": "残影，鬼影，半透明残像",
    "unnatural_movement": "身体变形，身体拉伸，动作不自然",
    "character_inconsistency": "风格改变，纹理重建，颜色失真",
    "background_color_change": "背景变色，背景变暗，背景变灰",
    "frame_escape": "画面外移动，超出边界",
    "no_return_to_origin": "动作不回归，姿势偏移",
    "speed_too_fast": "动作过快，快速移动",
}
QUALITY_ISSUES = {"unnatural_movement", "character_inconsistency"}
MOTION_ONLY_ISSUES = {"no_motion", "too_slow"}
SOFT_ISSUES = {"background_color_change"}
CONSECUTIVE_FAIL_THRESHOLD = 2


@dataclass
class LoopState:
    """Mutable state for the retry loop."""

    analysis: VisionAnalysis
    mask_path: Path | None = None
    current_fps: int = 0
    current_scale: float = 0.65
    adj_positive: str = ""
    adj_negative: str = ""
    consecutive_quality: int = 0
    consecutive_nomotion: int = 0
    _base_positive: str = ""
    _base_negative: str = ""

    def __post_init__(self) -> None:
        self.current_fps = self.analysis.frame_rate
        self.rebuild_base_prompts()

    def rebuild_base_prompts(self) -> None:
        bg_pos = (
            "纯白色背景，背景始终保持白色，边缘锐利，无残影"
            if self.analysis.bg_type == "solid"
            else "背景保持不变，画面清晰"
        )
        bg_neg = (
            "背景变色，背景变暗，背景变灰，黑屏"
            if self.analysis.bg_type == "solid"
            else "背景消失，背景模糊"
        )
        self._base_positive = bg_pos + ", " + self.analysis.positive
        self._base_negative = self.analysis.negative + ", " + bg_neg

    def build_prompts(self) -> tuple[str, str]:
        pos = self._base_positive
        if self.adj_positive:
            pos += ", " + self.adj_positive
        neg = self._base_negative
        if self.adj_negative:
            neg += ", " + self.adj_negative
        return pos, neg
