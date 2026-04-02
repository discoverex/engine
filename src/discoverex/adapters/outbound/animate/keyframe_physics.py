"""Physics helper functions for keyframe generation."""

from __future__ import annotations

import math


def damped_sin(t: float, amplitude: float, omega: float, lam: float) -> float:
    """Damped sine wave: A * sin(wt) * e^(-lt)."""
    return amplitude * math.sin(omega * t) * math.exp(-lam * t)


def damped_cos(t: float, amplitude: float, omega: float, lam: float) -> float:
    """Damped cosine wave: A * cos(wt) * e^(-lt)."""
    return amplitude * math.cos(omega * t) * math.exp(-lam * t)
