"""Travel/physics keyframe generators — launch, float, parabolic, hop."""

from __future__ import annotations

import math

from discoverex.domain.animate_keyframe import KeyframeAnimation, KFKeyframe


def gen_launch(facing: str, dur: int | None) -> KeyframeAnimation:
    duration = dur or 2000
    dist = 300
    dx, dy = 0, 0
    if facing == "up":
        dy = -dist
    elif facing == "down":
        dy = dist
    elif facing == "left":
        dx = -dist
    elif facing == "right":
        dx = dist
    else:
        dy = -dist
    kfs = [
        KFKeyframe(t=0.00, translateX=0, translateY=0),
        KFKeyframe(t=0.05, translateX=dx * 0.02, translateY=dy * 0.02, scaleX=1.02, scaleY=0.98),
        KFKeyframe(t=0.15, translateX=dx * 0.15, translateY=dy * 0.15),
        KFKeyframe(t=0.35, translateX=dx * 0.50, translateY=dy * 0.50),
        KFKeyframe(t=0.55, translateX=dx * 0.75, translateY=dy * 0.75),
        KFKeyframe(t=0.75, translateX=dx * 0.90, translateY=dy * 0.90),
        KFKeyframe(t=0.90, translateX=dx * 0.97, translateY=dy * 0.97),
        KFKeyframe(t=1.00, translateX=float(dx), translateY=float(dy)),
    ]
    return KeyframeAnimation(
        animation_type="launch", keyframes=kfs, duration_ms=duration,
        easing="ease-out", transform_origin="center center", loop=False,
    )


def gen_float(facing: str, dur: int | None) -> KeyframeAnimation:
    duration = dur or 3000
    fh, sx, tilt, steps = 20, 5, 3, 8
    kfs = []
    for i in range(steps):
        t = i / (steps - 1)
        phase = t * 2 * math.pi
        kfs.append(KFKeyframe(
            t=t,
            translateX=round(sx * math.cos(phase), 2),
            translateY=round(-fh * math.sin(phase), 2),
            rotate=round(tilt * math.sin(phase), 2),
            scaleY=round(1.0 + 0.02 * math.sin(phase), 3),
        ))
    kfs[-1].translateX = kfs[0].translateX
    kfs[-1].translateY = kfs[0].translateY
    kfs[-1].rotate = kfs[0].rotate
    kfs[-1].scaleY = kfs[0].scaleY
    return KeyframeAnimation(
        animation_type="float", keyframes=kfs, duration_ms=duration,
        easing="ease-in-out", transform_origin="center center", loop=True,
    )


def gen_parabolic(facing: str, dur: int | None) -> KeyframeAnimation:
    duration = dur or 1500
    rx, py = 200, 120
    direction = -1 if facing == "left" else 1
    steps = 8
    kfs = []
    for i in range(steps):
        t = i / (steps - 1)
        dx = direction * rx * t
        dy = -4 * py * t * (1 - t)
        rot = direction * 15 * (1 - 2 * t)
        s = 1.0 - 0.08 * math.sin(math.pi * t)
        kfs.append(KFKeyframe(
            t=round(t, 3), translateX=round(dx, 2), translateY=round(dy, 2),
            rotate=round(rot, 2), scaleX=round(s, 3), scaleY=round(s, 3),
        ))
    return KeyframeAnimation(
        animation_type="parabolic", keyframes=kfs, duration_ms=duration,
        easing="linear", transform_origin="center center", loop=False,
    )


def gen_hop(facing: str, dur: int | None) -> KeyframeAnimation:
    duration = dur or 1200
    height, steps = 60, 8
    kfs = []
    for i in range(steps):
        t = i / (steps - 1)
        dy = -4 * height * t * (1 - t)
        kfs.append(KFKeyframe(t=round(t, 3), translateY=round(dy, 2)))
    kfs[-1].translateY = 0.0
    return KeyframeAnimation(
        animation_type="hop", keyframes=kfs, duration_ms=duration,
        easing="ease-in-out", transform_origin="center bottom", loop=True,
    )
