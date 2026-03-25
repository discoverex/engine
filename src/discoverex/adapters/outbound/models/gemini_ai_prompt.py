"""System prompt for Gemini AI Validator (assembled from parts).

Source: wan_ai_validator.py lines 70-322 (original full prompt).
"""

from .gemini_ai_prompt_criteria import _AI_PART1, _AI_PART2
from .gemini_ai_prompt_fixes import _AI_PART3

AI_VALIDATOR_SYSTEM_PROMPT = _AI_PART1 + _AI_PART2 + _AI_PART3
