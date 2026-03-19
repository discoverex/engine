"""Vision prompt text constants (PART2 + PART3) — Steps 5-8 + Output Format.

Source: wan_vision_analyzer.py lines 170-299.
"""

# ruff: noqa: E501
_VISION_PART2 = """
STEP 5 — WRITE PROMPTS
Keep prompts SHORT and CLEAR. Do NOT use pixel coordinates or repeat phrases.
⚠️ WRITE BOTH positive AND negative IN CHINESE (简体中文). WAN was trained on Chinese data.

Positive (under 60 words in Chinese):
  Line 1: subject type, color, art style
  Line 2: the moving part and how it moves — describe the motion as a small arc or tilt
  Line 3: which parts stay completely still — explicitly state "身体完全静止，不旋转"
  Line 4: background, loop, quality keywords

  MOTION EXPRESSION GUIDE:
    For small arc/sweep motion: "小幅度来回摆动", "轻轻摆动", "小幅摆动"
    For tilt/nod motion: "轻轻点头", "小幅度倾斜后复位"
    For lift/lower motion: "轻轻抬起后放下", "小幅度上下运动"
    The motion must be described as returning to start: always include "来回" or "后复位"

  FORBIDDEN words (cause whole-body rotation or drift):
    "旋转", "转身", "扭动", "摇摆身体", "全身运动"
    Do NOT use: any phrase that implies the whole body rotates or translates

  For the SPECIAL CASE (full body jump):
    - 身体向上跳起后落回原位附近
    - 保持画面中央，不左右移动
    - 动作完整循环，结束姿势接近开始姿势

Negative (under 40 words in Chinese):
  Focus on the most likely failures for this specific motion.
  Always include: body rotation, body drift, and any volumetric-only changes.
  For small-part motions: also include whole-body movement and the part freezing.
  Always include these two universal failure patterns:
    - 身体消失，角色部位缺失  (body/part disappearing mid-animation)
    - 背景出现灰色区域，背景变色  (grey box or color stain appearing in background)

STEP 6 — MOTION THRESHOLDS
  Set based on the spatial range of the chosen motion:
  Large range (motion covers >20% of image): min=0.05~0.08, max=0.20~0.35
  Medium range (motion covers 10~20% of image): min=0.03~0.06, max=0.12~0.25
  Small range (motion covers <10% of image): min=0.02~0.04, max=0.08~0.15
  max_diff = max_motion × 1.5

STEP 7 — FRAME COUNT
  Decide how many frames WAN should generate (BEFORE pingpong doubling).
  WAN constraint: minimum 9, maximum 81 frames.
  Choose based on the motion type:

  SHORT (17–21 frames): Fast repeating cycles that need only one simple arc.
    Use when: the motion is a small, quick sweep or flick that completes in under 1 second.
    Examples: wing lower-and-return, tail flick, head bob, ear twitch
    Reasoning: fewer frames = less time for WAN to introduce deformation artifacts.

  MEDIUM (25–33 frames): Motions that require a clear arc with visible peak displacement.
    Use when: the motion has a moderate range and needs ~1–1.5 seconds to look natural.
    Examples: tail sweep, fin wave, body sway, leg lift

  LONG (33–49 frames): Full-cycle motions where the complete action must be visible.
    Use when: the motion has multiple distinct phases (launch → peak → land).
    Examples: frog jump (crouch → launch → airborne → land),
              fish full-body S-curve, full wing flap cycle
    Reasoning: cutting these short makes the motion look incomplete or abrupt.

  RULE: When in doubt, choose SHORT over LONG.
  Fewer frames reduce generation artifacts and keep the loop tight."""

_VISION_PART3 = """
STEP 8 — LOOP TYPE & BACKGROUND
  Analyze the image to determine:

  A) PINGPONG (loop direction):
     Determine whether the animation should play forward-then-backward (pingpong)
     or forward-only (one-directional loop).

     ━━━ CORE PRINCIPLE ━━━
     Ask yourself: "If this image were a real moment frozen in time,
     would the subject RETURN to the starting state, or CONTINUE forward?"

     Then ask: "Is the subject moving in ONE DIRECTION through space?"
     If the subject, or anything in the scene, is traveling in a single
     direction (forward, away, upward, etc.), pingpong MUST be false.
     The direction of travel does not reverse in reality.

     IMPORTANT: Judge by the POSE, not the background.
     A subject can be walking/running/riding even on a white or solid background.
     Look at the body pose: are the legs mid-stride? Is the body leaning forward?
     Is the subject seen from behind, moving away? These all mean pingpong = false,
     regardless of whether the background is solid white or a detailed scene.

     pingpong = false (continue forward):
       The image implies ongoing movement through space or time.
       The subject's pose suggests travel (walking, running, riding, flying away).
       If you played it backward, it would look unnatural.

     pingpong = true (return to start):
       The image implies a stationary subject doing a repeating motion.
       The subject's pose is static (standing, sitting, perching, hovering).
       Nothing in the scene is traveling in any direction.
       Playing it forward then backward would look natural.

  B) BACKGROUND TYPE:
     bg_type = "solid":
       - Background is white, single color, or simple gradient
       - No environmental elements (no road, sky, trees, buildings)

     bg_type = "scene":
       - Background contains environmental elements (road, sky, forest, room, city)
       - Background is part of the content and should NOT be removed

  C) BACKGROUND REMOVAL:
     bg_remove = true:  when bg_type is "solid" (remove and make transparent)
     bg_remove = false: when bg_type is "scene" (keep background as-is)

OUTPUT FORMAT
Respond ONLY with JSON. No text outside JSON. No markdown fences.

{
  "object_desc": "subject appearance and visible body parts",
  "action_desc": "chosen action",
  "moving_parts": "only the parts that move",
  "fixed_parts": "all parts that stay frozen",
  "moving_zone": [x1, y1, x2, y2],
  "reason": "why this action and part isolation",
  "frame_rate": <integer 8-24>,
  "frame_count": <integer 9-81>,
  "min_motion": <float 0.02-0.25>,
  "max_motion": <float 0.08-0.80>,
  "max_diff": <float max_motion*1.5>,
  "positive": "<중국어 positive 프롬프트, 60단어 이내>",
  "negative": "<중국어 negative 프롬프트, 40단어 이내>",
  "pingpong": <true or false>,
  "bg_type": "<solid or scene>",
  "bg_remove": <true or false>
}"""
