"""BackgroundRemovalPort implementation — transparent PNG sequence from video.

Extracts frames, detects background via flood-fill, removes background.
APNG/WebM generation is delegated to FormatConversionPort.

Dependencies: PIL, numpy, scipy, ffmpeg (subprocess).
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
from scipy import ndimage

from discoverex.domain.animate_keyframe import TransparentSequence

logger = logging.getLogger(__name__)


class FfmpegBgRemover:
    """Remove background from video frames → transparent PNG sequence.

    Uses original image silhouette as protection mask to preserve
    character pixels (e.g. white wings) that match the background color.
    """

    def __init__(self, tolerance: int = 50) -> None:
        self.tolerance = tolerance

    def remove(self, video: Path, fps: int = 16) -> TransparentSequence:
        frames = _extract_raw_frames(str(video))
        if not frames:
            raise RuntimeError(f"Frame extraction failed: {video}")

        bg_color = _detect_bg_color(frames[0])
        is_dark_bg = bg_color.mean() < 128
        protect = None if is_dark_bg else _build_protect_mask(video, bg_color, self.tolerance)
        if is_dark_bg:
            logger.info("[BgRemover] dark bg (%.0f) → protection mask skipped", bg_color.mean())
        output_dir = video.parent / f"{video.stem}_transparent"
        output_dir.mkdir(parents=True, exist_ok=True)

        result_paths: list[Path] = []
        for i, frame in enumerate(frames):
            rgba = _remove_bg_frame(frame, bg_color, self.tolerance, protect)
            out = output_dir / f"{video.stem}_frame_{i:04d}.png"
            rgba.save(out, "PNG")
            result_paths.append(out)

        logger.info(f"[BgRemover] {len(result_paths)} frames saved: {output_dir}")
        return TransparentSequence(frames=result_paths)


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


def _build_protect_mask(
    video: Path, bg_color: np.ndarray, tolerance: int,
) -> np.ndarray | None:
    """Build character protection mask from original image alpha or silhouette."""
    import re
    stem = re.sub(r"_a\d+$", "", video.stem)
    # 1. preprocessed 이미지 (같은 디렉토리)
    orig_processed = video.parent / f"{stem}.png"
    # 2. 원본 입력 이미지 (ComfyUI input 등) — alpha 채널 활용
    orig_input = _find_original_input(video, stem)
    # Alpha 채널 우선 사용
    if orig_input and orig_input.exists():
        img = Image.open(orig_input)
        if img.mode == "RGBA":
            alpha = np.array(img)[:, :, 3]
            protect = alpha > 128  # 불투명 = 캐릭터
            # preprocessed 크기에 맞추기
            if orig_processed.exists():
                target = Image.open(orig_processed).convert("RGB")
                th, tw = np.array(target).shape[:2]
                if protect.shape != (th, tw):
                    resized = Image.fromarray(protect.astype(np.uint8) * 255).resize((tw, th), Image.NEAREST)
                    protect = np.array(resized) > 128
            logger.info("[BgRemover] alpha mask: %d%% character", int(protect.sum() / protect.size * 100))
            return protect
    # Fallback: flood-fill 기반
    if orig_processed and orig_processed.exists():
        img_arr = np.array(Image.open(orig_processed).convert("RGB"))
        is_bg = np.all(np.abs(img_arr.astype(int) - bg_color) < tolerance, axis=2)
        labeled, _ = ndimage.label(is_bg)
        h, w = img_arr.shape[:2]
        bl = set(labeled[0,:].tolist()) | set(labeled[-1,:].tolist()) | set(labeled[:,0].tolist()) | set(labeled[:,-1].tolist())
        bl.discard(0)
        bg_m = np.zeros((h, w), dtype=bool)
        for lbl in bl:
            bg_m |= labeled == lbl
        protect = ~bg_m
        logger.info("[BgRemover] silhouette mask: %d%% character", int(protect.sum() / protect.size * 100))
        return protect
    return None


def _find_original_input(video: Path, stem: str) -> Path | None:
    """Find original input image with alpha channel."""
    import re
    base = re.sub(r"_processed$", "", stem)
    candidates = [
        Path.home() / "ComfyUI" / "input" / f"{base}.png",
        video.parent.parent.parent / "input" / f"{base}.png",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _remove_bg_frame(
    frame: np.ndarray, bg_color: np.ndarray, tolerance: int,
    protect: np.ndarray | None = None,
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
    # Protect character pixels from original image silhouette
    if protect is not None and protect.shape == (h, w):
        bg_mask &= ~protect

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, :3] = frame
    rgba[:, :, 3] = 255
    rgba[bg_mask, 3] = 0
    return Image.fromarray(rgba, "RGBA")
