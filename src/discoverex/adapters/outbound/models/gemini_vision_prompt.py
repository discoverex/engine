"""System prompt for Gemini Vision Analyzer (assembled from parts).

Source: wan_vision_analyzer.py lines 58-299 (original full prompt).
"""

from .gemini_vision_prompt_parts import _VISION_PART1
from .gemini_vision_prompt_steps import _VISION_PART2, _VISION_PART3

VISION_SYSTEM_PROMPT = _VISION_PART1 + _VISION_PART2 + _VISION_PART3
