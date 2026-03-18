"""Frame extraction and background detection utilities for animation validation."""

from __future__ import annotations

import glob
import logging
import subprocess
import tempfile
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def extract_frames(video_path: str, size: int = 240) -> list[Any]:
    """Extract frames from MP4 via ffmpeg → numpy float32 list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "ffmpeg", "-i", video_path,
            "-vf", f"scale={size}:{size}",
            f"{tmpdir}/frame_%04d.png",
            "-y", "-loglevel", "quiet",
        ]
        ret = subprocess.run(cmd, capture_output=True)  # noqa: S603
        if ret.returncode != 0:
            logger.error(f"[Validator] ffmpeg failed: {ret.stderr.decode()}")
            return []

        paths = sorted(glob.glob(f"{tmpdir}/frame_*.png"))
        return [
            np.array(Image.open(p).convert("RGB"), dtype=np.float32) / 255.0
            for p in paths
        ]


def detect_bg_color(frame: np.ndarray) -> Any:
    """Detect background color from border pixels of first frame."""
    h, w, _ = frame.shape
    bs = max(3, h // 20)
    border = np.concatenate([
        frame[:bs, :, :].reshape(-1, 3),
        frame[-bs:, :, :].reshape(-1, 3),
        frame[:, :bs, :].reshape(-1, 3),
        frame[:, -bs:, :].reshape(-1, 3),
    ])
    return border.mean(axis=0)


def get_bg_mask(
    frame: np.ndarray,
    bg_color: np.ndarray,
    tolerance: float = 30,
) -> Any:
    """Return background mask (True = background, False = character)."""
    tol = tolerance / 255.0
    return np.all(np.abs(frame.astype(float) - bg_color) < tol, axis=2)
