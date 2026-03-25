"""AI Validator prompt — Issue Adjustments + Output Format (PART3).

Source: wan_ai_validator.py lines 240-322 (original full prompt).
"""

# ruff: noqa: E501
_AI_PART3 = """
═══════════════════════════════════════════════════════
IF ISSUES ARE FOUND — PROVIDE SPECIFIC ADJUSTMENTS
═══════════════════════════════════════════════════════
You must provide concrete fixes, NOT vague suggestions.

For NO MOTION or TOO SLOW (character barely moves):
  - STEP A: Look at the current positive prompt and identify which body part is currently targeted.
  - STEP B: Judge whether that body part can produce VISIBLE motion in WAN.
    Apply this filter — the target part FAILS if any of these are true:
      ❌ It only swells/pulsates without sweeping through space (belly, throat)
      ❌ Its pixel change is too small to detect (eyelid, skin color)
      ❌ It must structurally deform to perform the motion (folding, bending at joint)
    A part PASSES if: it moves through space while keeping its shape (sweep, tilt, lift, rotate)
  - STEP C: If the current target FAILS the filter → SWITCH to a different part.
    Look at the character in the video and find a part that:
      ✅ Is clearly visible and distinct from the body
      ✅ Can sweep/tilt/rotate while keeping its shape
      ✅ Is small relative to the whole character (roughly 10–25% of the image)
    Do NOT suggest specific body parts by name — choose based on what is visible in this specific image.
  - STEP D: Rewrite positive_addition for the new target (in Chinese).
    Pattern: "[该部位] 轻轻运动，保持形状不变，小幅度来回摆动"
    The part must move as a rigid unit — no folding, no deformation.
  - STEP E: Increase frame_rate by 2 (e.g., 12→14, 14→16, 16→18).
  - STEP F: negative_addition is MANDATORY for no_motion/too_slow.
    Add: any part currently moving that should be frozen, plus "身体晃动，身体摇摆"
    e.g. if wrong part moves: add "[that part]移动，[that part]运动"
  - STEP G: NEVER copy motion phrases from positive into negative — this cancels the motion.
    Negative describes unwanted outcomes only, never the intended motion itself.
  - NEVER amplify an already-failed target — switch instead.

For speed issues (too fast):
  - Decrease frame_rate (e.g., 10, 12, 14)
  - Add to negative_addition: "动作过快，快速移动，急速运动" to reinforce the slow-down

For naturalness/character issues:
  - NEGATIVE IS PRIMARY: first identify the exact visual problem and block it with negative
    e.g. body distortion → "身体变形，身体拉伸，身体扭曲"
    e.g. unnatural arc → "[该部位]运动不自然，[该部位]轨迹突变，[该部位]抖动"
    e.g. character style change → "风格改变，线条模糊，颜色失真，卡通风格丢失"
    e.g. part morphing → "[该部位]变形，[该部位]拉伸，形状改变"
    Replace [该部位] with the actual moving part observed in the video.
  - POSITIVE is secondary: only add if the specific motion needs reinforcing
    e.g. "[该部位]平滑运动，保持形状" (only if the moving part's motion needs reinforcing)
  - RULE: negative_addition must ALWAYS be provided for naturalness/character issues
    positive_addition may be null if negative alone is sufficient

For frame escape:
  - Suggest scale reduction (e.g., 0.55 instead of 0.65)

For background color change (background turns black, purple, grey, yellow):
  - This is a critical WAN generation failure
  - Do NOT change frame_rate — set frame_rate to null
  - Do NOT change scale — set scale to null
  - Only add background prompts, do not touch motion prompts
  - Add to positive (in Chinese): "纯白色背景，整个动画过程中背景始终保持白色"
  - Add to negative (in Chinese): "背景变色，背景变暗，背景变黑，背景变灰，背景变黄，背景变紫，背景颜色偏移，非白色背景"

For return-to-origin:
  - Add to positive: "动作完整循环，结束时回到接近开始的姿势，保持画面中央"
  - Add to negative: "动作不完整，停在最高点，动作中途结束，水平方向漂移"
  - NOTE: for motions where the whole body moves as a rigid unit (e.g. a full body jump/leap),
    exact pixel return is NOT required — returning close to origin is acceptable.
    Only fail if the subject drifts far from center or freezes at peak without returning.

═══════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════
Respond ONLY with JSON. No text outside JSON. No markdown fences.

CRITICAL: Keep the "reason" field under 20 words. Do NOT use newlines, quotes, or
special characters inside the reason string — this will break JSON parsing.

{
  "passed": <true|false>,
  "issues": ["speed_too_fast"|"speed_too_slow"|"no_motion"|"no_return_to_origin"|"frame_escape"|"unnatural_movement"|"character_inconsistency"|"background_color_change"],
  "reason": "one short sentence, under 20 words, no quotes or newlines",
  "adjustments": {
    "frame_rate": <integer or null>,
    "scale": <float or null>,
    "positive_addition": "<specific phrases to ADD to positive prompt, or null>",
    "negative_addition": "<specific phrases to ADD to negative prompt, or null>"
  }
}"""
