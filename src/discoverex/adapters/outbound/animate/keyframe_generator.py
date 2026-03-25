"""KeyframeGenerationPort implementation — CSS keyframe animation generator.

Maps suggested_action to physics-based keyframe sequences.
Pure computation — no external dependencies beyond math.
"""

from __future__ import annotations

import logging
import math

from discoverex.domain.animate_keyframe import (
    KeyframeAnimation,
    KeyframeConfig,
    KFKeyframe,
)

from .keyframe_physics import damped_sin
from .keyframe_travel import gen_float, gen_hop, gen_launch, gen_parabolic

logger = logging.getLogger(__name__)


class PilKeyframeGenerator:
    """Generate CSS keyframe animations from KeyframeConfig."""

    def generate(self, config: KeyframeConfig) -> KeyframeAnimation:
        facing = config.facing_direction
        dur = config.duration_ms
        action = config.suggested_action

        if action == "nudge_horizontal":
            anim = self._gen_nudge_h(facing, dur)
        elif action == "nudge_vertical":
            anim = self._gen_nudge_v(facing, dur)
        elif action == "spin":
            anim = self._gen_spin(facing, dur)
        elif action == "bounce":
            anim = self._gen_bounce(facing, dur)
        elif action == "pop":
            anim = self._gen_pop(facing, dur)
        elif action == "launch":
            anim = gen_launch(facing, dur)
        elif action == "float":
            anim = gen_float(facing, dur)
        elif action == "parabolic":
            anim = gen_parabolic(facing, dur)
        elif action == "hop":
            anim = gen_hop(facing, dur)
        else:
            anim = self._gen_wobble(facing, dur)
        if config.suggested_action not in ("launch", "parabolic"):
            anim.loop = config.loop
        anim.suggested_action = config.suggested_action
        anim.facing_direction = config.facing_direction

        logger.info(
            f"[KeyframeGen] {config.suggested_action} "
            f"facing={config.facing_direction} -> "
            f"{anim.animation_type} {anim.duration_ms}ms "
            f"{len(anim.keyframes)} keyframes"
        )
        return anim

    def _gen_nudge_h(self, facing: str, dur: int | None) -> KeyframeAnimation:
        duration = dur or 1200
        direction = -1 if facing == "left" else 1
        omega, lam, steps, distance = 2 * math.pi * 2, 1.5, 8, 20
        kfs = []
        for i in range(steps):
            t = i / (steps - 1)
            dx = direction * damped_sin(t * duration / 1000, distance, omega, lam)
            kfs.append(KFKeyframe(t=t, translateX=dx))
        kfs[-1].translateX = 0.0
        return KeyframeAnimation(
            animation_type="nudge", keyframes=kfs, duration_ms=duration,
            easing="ease-out", transform_origin="center center",
        )

    def _gen_nudge_v(self, facing: str, dur: int | None) -> KeyframeAnimation:
        duration = dur or 1000
        direction = -1 if facing == "up" else 1
        omega, lam, steps, distance = 2 * math.pi * 2, 1.8, 8, 18
        kfs = []
        for i in range(steps):
            t = i / (steps - 1)
            dy = direction * damped_sin(t * duration / 1000, distance, omega, lam)
            kfs.append(KFKeyframe(t=t, translateY=dy))
        kfs[-1].translateY = 0.0
        return KeyframeAnimation(
            animation_type="nudge", keyframes=kfs, duration_ms=duration,
            easing="ease-out", transform_origin="center center",
        )

    def _gen_wobble(self, facing: str, dur: int | None) -> KeyframeAnimation:
        duration = dur or 1500
        amplitude, omega, lam, steps = 12, 2 * math.pi * 2.5, 1.2, 8
        kfs = []
        for i in range(steps):
            t = i / (steps - 1)
            angle = damped_sin(t * duration / 1000, amplitude, omega, lam)
            sy = 1.0 + abs(angle) / amplitude * 0.04
            kfs.append(KFKeyframe(t=t, rotate=angle, scaleY=sy))
        kfs[-1].rotate = 0.0
        kfs[-1].scaleY = 1.0
        return KeyframeAnimation(
            animation_type="wobble", keyframes=kfs, duration_ms=duration,
            easing="ease-in-out", transform_origin="center center",
        )

    def _gen_spin(self, facing: str, dur: int | None) -> KeyframeAnimation:
        duration = dur or 1000
        kfs = [
            KFKeyframe(t=0.00, scaleX=1.00, scaleY=1.00),
            KFKeyframe(t=0.25, scaleX=0.02, scaleY=1.08),
            KFKeyframe(t=0.50, scaleX=1.00, scaleY=1.04),
            KFKeyframe(t=0.75, scaleX=0.02, scaleY=1.08),
            KFKeyframe(t=1.00, scaleX=1.00, scaleY=1.00),
        ]
        return KeyframeAnimation(
            animation_type="spin", keyframes=kfs, duration_ms=duration,
            easing="linear", transform_origin="center center",
        )

    def _gen_bounce(self, facing: str, dur: int | None) -> KeyframeAnimation:
        duration = dur or 800
        h = 15
        kfs = [
            KFKeyframe(t=0.00, translateY=0, scaleX=1.00, scaleY=1.00),
            KFKeyframe(t=0.15, translateY=0, scaleX=1.10, scaleY=0.90),
            KFKeyframe(t=0.40, translateY=-h, scaleX=0.92, scaleY=1.12),
            KFKeyframe(t=0.60, translateY=-h * 0.3, scaleX=1.02, scaleY=0.98),
            KFKeyframe(t=0.75, translateY=0, scaleX=1.06, scaleY=0.94),
            KFKeyframe(t=0.90, translateY=-h * 0.1, scaleX=0.98, scaleY=1.02),
            KFKeyframe(t=1.00, translateY=0, scaleX=1.00, scaleY=1.00),
        ]
        return KeyframeAnimation(
            animation_type="jump", keyframes=kfs, duration_ms=duration,
            easing="ease-out", transform_origin="center bottom",
        )

    def _gen_pop(self, facing: str, dur: int | None) -> KeyframeAnimation:
        duration = dur or 500
        kfs = [
            KFKeyframe(t=0.00, scaleX=1.00, scaleY=1.00),
            KFKeyframe(t=0.30, scaleX=1.08, scaleY=1.08),
            KFKeyframe(t=0.60, scaleX=1.03, scaleY=1.03),
            KFKeyframe(t=1.00, scaleX=1.00, scaleY=1.00),
        ]
        return KeyframeAnimation(
            animation_type="pop", keyframes=kfs, duration_ms=duration,
            easing="ease-out", transform_origin="center center",
        )

