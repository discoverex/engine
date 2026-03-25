"""FormatConversionPort implementation — APNG, WebM, Lottie conversion.

Converts transparent PNG sequence to web-ready formats.
Dependencies: PIL, ffmpeg (subprocess for WebM).
"""

from __future__ import annotations

import base64
import io
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from discoverex.domain.animate_keyframe import ConvertedAsset

logger = logging.getLogger(__name__)

OPTIMIZE_PRESETS: dict[str, dict[str, Any]] = {
    "original": {"max_size": None, "max_frames": None, "png_optimize": False},
    "web": {"max_size": 240, "max_frames": 30, "png_optimize": True},
    "web_hd": {"max_size": 360, "max_frames": 40, "png_optimize": True},
    "mobile": {"max_size": 180, "max_frames": 24, "png_optimize": True},
}


class MultiFormatConverter:
    """Convert transparent PNG frames to APNG + WebM + Lottie JSON."""

    def convert(
        self, frames: list[Path], preset: str = "original", fps: int = 16,
    ) -> ConvertedAsset:
        if not frames:
            raise FileNotFoundError("No PNG frames provided")

        output_dir = frames[0].parent
        stem = frames[0].stem.rsplit("_frame_", 1)[0]

        p = OPTIMIZE_PRESETS.get(preset, OPTIMIZE_PRESETS["web"])
        selected = _select_frames(frames, p.get("max_frames"))

        apng_path = _save_apng(selected, output_dir / f"{stem}.apng", fps)
        webm_path = _save_webm(frames, output_dir / f"{stem}.webm", fps, stem)
        lottie_path = _save_lottie(
            selected, output_dir / f"{stem}.json", fps,
            p.get("max_size"), p.get("png_optimize", True),
        )

        return ConvertedAsset(
            apng_path=apng_path, webm_path=webm_path, lottie_path=lottie_path,
        )

    def convert_with_opts(
        self, frames: list[Path], fps: int = 16,
        max_size: int | None = None, max_frames: int | None = None,
        png_optimize: bool = True, **_: Any,
    ) -> ConvertedAsset:
        """Convert with explicit size/frame options (for target_size slider)."""
        if not frames:
            raise FileNotFoundError("No PNG frames provided")
        output_dir = frames[0].parent
        stem = frames[0].stem.rsplit("_frame_", 1)[0]
        selected = _select_frames(frames, max_frames)
        apng_path = _save_apng(selected, output_dir / f"{stem}.apng", fps)
        webm_path = _save_webm(frames, output_dir / f"{stem}.webm", fps, stem)
        lottie_path = _save_lottie(selected, output_dir / f"{stem}.json", fps, max_size, png_optimize)
        return ConvertedAsset(apng_path=apng_path, webm_path=webm_path, lottie_path=lottie_path)


def _detect_union_bbox(
    frames: list[Path], threshold: int = 10,
) -> tuple[int, int, int, int] | None:
    """전체 프레임의 통합 bbox — 모션 범위 전체를 포함."""
    import numpy as np
    g = [99999, 99999, 0, 0]  # c0, r0, c1, r1
    found = False
    for path in frames:
        a = np.array(Image.open(path).convert("RGBA"))[:, :, 3]
        rs, cs = np.any(a > threshold, axis=1), np.any(a > threshold, axis=0)
        if not rs.any():
            continue
        found = True
        g[1] = min(g[1], int(np.argmax(rs)))
        g[3] = max(g[3], int(len(rs) - np.argmax(rs[::-1])))
        g[0] = min(g[0], int(np.argmax(cs)))
        g[2] = max(g[2], int(len(cs) - np.argmax(cs[::-1])))
    return tuple(g) if found else None  # type: ignore[return-value]


def _select_frames(frames: list[Path], max_frames: int | None) -> list[Path]:
    if not max_frames or len(frames) <= max_frames:
        return frames
    step = len(frames) / max_frames
    indices = [int(i * step) for i in range(max_frames)]
    if indices[-1] != len(frames) - 1:
        indices[-1] = len(frames) - 1
    return [frames[i] for i in indices]


def _save_apng(frames: list[Path], out: Path, fps: int) -> Path | None:
    try:
        imgs = [Image.open(f).convert("RGBA") for f in frames]
        duration_ms = int(1000 / fps)
        imgs[0].save(
            out, format="PNG", save_all=True, append_images=imgs[1:],
            loop=0, duration=duration_ms, disposal=2,
        )
        logger.info(f"[Format] APNG saved: {out}")
        return out
    except Exception as e:
        logger.warning(f"[Format] APNG failed: {e}")
        return None


def _save_webm(
    frames: list[Path], out: Path, fps: int, stem: str,
) -> Path | None:
    try:
        pattern = str(frames[0].parent / f"{stem}_frame_%04d.png")
        cmd = [
            "ffmpeg", "-framerate", str(fps), "-i", pattern,
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
            "-b:v", "0", "-crf", "30", "-auto-alt-ref", "0",
            "-y", "-loglevel", "quiet", str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)  # noqa: S603
        if result.returncode == 0:
            logger.info(f"[Format] WebM saved: {out}")
            return out
        logger.warning(f"[Format] WebM ffmpeg failed: {result.stderr.decode()[:200]}")
        return None
    except Exception as e:
        logger.warning(f"[Format] WebM failed: {e}")
        return None


def _save_lottie(
    frames: list[Path], out: Path, fps: int,
    max_size: int | None, png_optimize: bool,
    canvas_scale: float = 4.0,
) -> Path | None:
    """Lottie JSON 생성.

    canvas_scale: 캔버스를 이미지 대비 몇 배로 할지 (원본 비율 유지).
      이미지 크기 유지, 캔버스 중앙 배치. 기준점(anchor)은 이미지 좌상단.
      프레임이 캔버스보다 클 경우 오브젝트 bbox로 크롭 후 max_size로 리사이즈.
    """
    try:
        first = Image.open(frames[0]).convert("RGBA")
        # 전체 프레임 통합 bbox — 모션 범위 전체 포함 (잘림 방지)
        crop_box = _detect_union_bbox(frames)
        iw = crop_box[2] - crop_box[0] if crop_box else first.size[0]
        ih = crop_box[3] - crop_box[1] if crop_box else first.size[1]

        # max_size로 리사이즈 (비율 유지)
        if max_size and max(iw, ih) > max_size:
            ratio = max_size / max(iw, ih)
            iw, ih = max(1, int(iw * ratio)), max(1, int(ih * ratio))

        cw = int(iw * canvas_scale) // 2 * 2 or 2
        ch = int(ih * canvas_scale) // 2 * 2 or 2
        img_x = (cw - iw) / 2
        img_y = (ch - ih) / 2

        assets, layers = [], []
        for i, path in enumerate(frames):
            img = Image.open(path).convert("RGBA")
            if crop_box:
                img = img.crop(crop_box)
            if img.size != (iw, ih):
                img = img.resize((iw, ih), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=png_optimize)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            assets.append({
                "id": f"frame_{i}", "w": iw, "h": ih,
                "u": "", "p": f"data:image/png;base64,{b64}", "e": 1,
            })
            layers.append({
                "ddd": 0, "ind": i, "ty": 2, "nm": f"frame_{i}",
                "refId": f"frame_{i}", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
                    "p": {"a": 0, "k": [img_x, img_y, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                },
                "ip": i, "op": i + 1, "st": 0, "bm": 0,
            })

        lottie = {
            "v": "5.7.0", "fr": fps, "ip": 0, "op": len(frames),
            "w": cw, "h": ch, "nm": out.stem, "ddd": 0,
            "assets": assets, "layers": layers,
        }
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(lottie, f, separators=(",", ":"))
        logger.info("[Format] Lottie saved: %s (img=%dx%d canvas=%dx%d)", out, iw, ih, cw, ch)
        return out
    except Exception as e:
        logger.warning(f"[Format] Lottie failed: {e}")
        return None
