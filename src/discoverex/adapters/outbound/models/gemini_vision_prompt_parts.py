"""Vision prompt text constants (PART1 + PART2 + PART3).

Source: wan_vision_analyzer.py lines 58-299 (original full prompt).
Kept in a separate file so the assembler stays under 200L.
"""

# ruff: noqa: E501
_VISION_PART1 = """You are an expert in WAN I2V (Image-to-Video) animation generation.
Analyze the image and return ALL parameters needed for a natural, loopable animation.

STEP 1 — IDENTIFY THE SUBJECT
Describe type, color, style, visible body parts.

STEP 2 — CHOOSE THE ACTION
Your goal is to choose the MOST NATURAL motion for this subject — the motion a viewer
would expect to see. Do NOT bias toward safer or simpler motions.
Natural motion produces better results than "easy" motion because WAN responds
to clear, characteristic intent.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE A — IDENTIFY THE IDENTITY MOTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Determine what kind of creature or object this is and what motion IS this subject.
Not what motion is safe — what motion makes this subject feel alive.

  SUBJECT TYPE → IDENTITY MOTION (always try this first):
    Bird / flying creature  → wing movement (flap, flutter, or raise/lower)
    Fish / aquatic creature → tail sweep + fin wave (swimming motion)
    Frog / jumping animal   → full body jump cycle
    Quadruped (dog, cat)    → tail wag, ear twitch
    Humanoid / character    → arm wave, torso sway
    Plant / tree            → leaf or branch sway
    Mechanical object       → gear rotation, antenna bob

  PRIORITY RULE: Always attempt the identity motion first.
    Head nods, tail twitches, and micro-motions are LAST RESORT fallbacks,
    used only after the identity motion has failed 3 times.
    Do NOT choose a safer alternative just to avoid risk.

  → Write down the IDENTITY MOTION for this subject before proceeding.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE B — FIND THE EXECUTABLE FORM OF THAT MOTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

WAN is a pixel-based model — it cannot fold, unfold, or structurally deform a part.
Find the form of the identity motion that WAN can physically execute.
This is about HOW to express the motion, not WHETHER to attempt it.

Apply these 3 filters to find the right form:

  Q1. IS IT LOOPABLE?
      Can the motion start and end at the same pose?
      ✅ PASS: pendulum swing, tail sweep, wing raise-and-return
      ❌ FAIL: flying off screen, jumping away, mouth staying open

  Q2. IS THE SHAPE PRESERVED DURING MOTION?
      Does the moving part keep its shape, or must it structurally deform?
      ✅ PASS: a wing lifting as a rigid unit, a tail sweeping, fins waving
      ❌ FAIL: a wing that must fold/unfold mid-flap, a mouth opening wide

      If the full form fails Q2, use a PARTIAL form — keep the intent:
        Bird wing full flap (fold/unfold) → ❌ too much deformation
        Bird wing: raises slightly and returns as rigid unit → ✅ same intent, achievable
        Fish full body S-curve wave → ❌ too much deformation
        Fish tail sweeps left-right (rigid) + fins sway gently → ✅ natural swimming feel

  Q3. IS THE MOTION RANGE VISIBLE AND BOUNDED?
      The motion should be clearly visible but not dominate the frame.
      ✅ PASS: motion covers 10–40% of the image area
      ❌ FAIL: invisible micro-motion (<5%) or full-frame takeover (>60%)

Only proceed with a motion that PASSES all 3 filters.
If the identity motion cannot pass in any form, fall back to the next most natural
motion for this subject — NOT the safest or smallest motion available.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALWAYS AVOID — regardless of subject type
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ❌ Volumetric change only (belly breathing, throat pulsation — no arc through space)
  ❌ Pixel-level changes too small to detect (eye blinking, skin color flush)
  ❌ Whole-body locomotion (subject moves its position across the frame)
  ❌ Body sway or drift with no clear returning motion

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPECIAL CASE — subjects with powerful jumping legs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  If the subject has large hind legs clearly built for leaping (the legs dominate
  the lower body and are visibly coiled/crouched):
    → A full jump cycle is acceptable: body rises then returns near origin
    → Must be horizontally centered, must complete the loop back near start
    → This is an exception because the whole body moves as a rigid unit (shape preserved)

STEP 3 — ISOLATE MOVING PARTS
Based on YOUR observation of the image, decide:
- MOVING: the single smallest part you identified in STEP 2
- FIXED: everything else — the entire body, head, torso must be completely frozen

The moving part should be visually distinct and small relative to the whole body.

STEP 3.5 — MOVING ZONE BBOX
Estimate the bounding box of the MOVING part in relative coordinates (0.0 to 1.0).
Origin is top-left. x1,y1 = top-left corner, x2,y2 = bottom-right corner.
  - Be GENEROUS: add 20% padding around the actual part so the motion has room.
  - The zone should cover the full arc of motion, not just the resting position.
  - Minimum zone size: 0.15 × 0.15 (to ensure meaningful denoising area)
  - For JUMPING creatures: zone covers the ENTIRE body [0.05, 0.05, 0.95, 0.95]
  Examples:
    Tail at bottom-right → [0.55, 0.60, 0.95, 0.95]
    Head nodding at top  → [0.20, 0.00, 0.80, 0.35]
    Fin on left side     → [0.00, 0.30, 0.35, 0.70]

STEP 4 — FRAME RATE
  Choose based on the natural speed of the chosen motion:
  Fast (small rapid repeating motion): 16–20 fps
  Medium (moderate arc, moderate speed): 12–16 fps
  Slow (large gentle motion): 8–12 fps"""
