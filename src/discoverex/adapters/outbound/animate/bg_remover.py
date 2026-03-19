"""BackgroundRemovalPort implementation — transparent PNG sequence from video.

Extracts frames via ffmpeg, removes background using rembg (U2Net).
APNG/WebM generation is delegated to FormatConversionPort.

Dependencies: PIL, numpy, ffmpeg (subprocess), rembg, onnxruntime.
"""

from __future__ import annotations

import glob
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from discoverex.domain.animate_keyframe import TransparentSequence

logger = logging.getLogger(__name__)


class RembgBgRemover:
    """Remove background from video frames using rembg (U2Net).

    Uses deep-learning salient object detection instead of color-based
    flood-fill, correctly preserving white objects on white backgrounds.
    """

    def __init__(self, model_name: str = "u2net") -> None:
        from rembg import new_session  # type: ignore[import-untyped]

        self._model_name = model_name
        self._session = new_session(model_name)
        logger.info("[BgRemover] rembg model loaded: %s", model_name)

    def remove(self, video: Path, fps: int = 16) -> TransparentSequence:
        frames = _extract_raw_frames(str(video))
        if not frames:
            raise RuntimeError(f"Frame extraction failed: {video}")

        output_dir = video.parent / f"{video.stem}_transparent"
        output_dir.mkdir(parents=True, exist_ok=True)

        from rembg import remove as rembg_remove  # type: ignore[import-untyped]

        result_paths: list[Path] = []
        for i, frame_arr in enumerate(frames):
            pil_img = Image.fromarray(frame_arr)
            rgba: Any = rembg_remove(pil_img, session=self._session)
            out = output_dir / f"{video.stem}_frame_{i:04d}.png"
            rgba.save(out, "PNG")
            result_paths.append(out)

        logger.info(
            "[BgRemover] %d frames saved (%s): %s",
            len(result_paths), self._model_name, output_dir,
        )
        return TransparentSequence(frames=result_paths)


# --- legacy flood-fill remover (kept for fallback / comparison) ---


class FfmpegBgRemover:
    """Remove background via color-based flood-fill (legacy).

    Known issue: cannot distinguish white objects from white backgrounds.
    Use RembgBgRemover instead for production.
    """

    def __init__(self, tolerance: int = 50) -> None:
        self.tolerance = tolerance

    def remove(self, video: Path, fps: int = 16) -> TransparentSequence:
        from scipy import ndimage

        frames = _extract_raw_frames(str(video))
        if not frames:
            raise RuntimeError(f"Frame extraction failed: {video}")

        bg_color = _detect_bg_color(frames[0])
        logger.info("[BgRemover] bg color: R=%.0f G=%.0f B=%.0f", *bg_color)
        output_dir = video.parent / f"{video.stem}_transparent"
        output_dir.mkdir(parents=True, exist_ok=True)

        result_paths: list[Path] = []
        for i, frame in enumerate(frames):
            rgba = _remove_bg_frame(frame, bg_color, self.tolerance, ndimage)
            out = output_dir / f"{video.stem}_frame_{i:04d}.png"
            rgba.save(out, "PNG")
            result_paths.append(out)

        logger.info(f"[BgRemover] {len(result_paths)} frames saved: {output_dir}")
        return TransparentSequence(frames=result_paths)


# --- shared helpers ---


def _extract_raw_frames(video_path: str) -> list[np.ndarray]:
    """Extract all frames from MP4 via ffmpeg (uint8, no scaling)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "ffmpeg", "-i", video_path,
            f"{tmpdir}/frame_%04d.png",
            "-y", "-loglevel", "quiet",
        ]
        ret = subprocess.run(cmd, capture_output=True)  # noqa: S603
        if ret.returncode != 0:
            return []
        paths = sorted(glob.glob(f"{tmpdir}/frame_*.png"))
        return [np.array(Image.open(p).convert("RGB")) for p in paths]


def _detect_bg_color(frame: np.ndarray) -> Any:
    h, w = frame.shape[:2]
    bs = max(3, h // 20)
    border = np.concatenate([
        frame[:bs, :, :].reshape(-1, 3), frame[-bs:, :, :].reshape(-1, 3),
        frame[:, :bs, :].reshape(-1, 3), frame[:, -bs:, :].reshape(-1, 3),
    ])
    return border.mean(axis=0)


def _remove_bg_frame(
    frame: np.ndarray, bg_color: np.ndarray, tolerance: int, ndimage: Any,
) -> Image.Image:
    h, w = frame.shape[:2]
    is_bg = np.all(np.abs(frame.astype(int) - bg_color) < tolerance, axis=2)
    labeled, _ = ndimage.label(is_bg)
    border_labels = (
        set(labeled[0, :].tolist()) | set(labeled[-1, :].tolist())
        | set(labeled[:, 0].tolist()) | set(labeled[:, -1].tolist())
    )
    border_labels.discard(0)
    bg_mask = np.zeros((h, w), dtype=bool)
    for lbl in border_labels:
        bg_mask |= labeled == lbl

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, :3] = frame
    rgba[:, :, 3] = 255
    rgba[bg_mask, 3] = 0
    return Image.fromarray(rgba, "RGBA")
