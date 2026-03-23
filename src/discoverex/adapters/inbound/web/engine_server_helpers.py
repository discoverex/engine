"""Helper utilities for engine_server."""

from __future__ import annotations

import glob
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from flask import jsonify, send_file

logger = logging.getLogger(__name__)

_MIME = {
    ".mp4": "video/mp4", ".webm": "video/webm",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".json": "application/json", ".apng": "image/apng", ".gif": "image/gif",
}


def video_list(motion_dir: Path, stem: str) -> list[dict[str, Any]]:
    if stem == "*":
        patterns = [str(motion_dir / "*.mp4")]
    else:
        patterns = [
            str(motion_dir / f"{stem}*_a*.mp4"),
            str(motion_dir / f"{stem}*attempt*.mp4"),
        ]
    seen: set[str] = set()
    vids = []
    for pattern in patterns:
        for p in sorted(glob.glob(pattern)):
            if p in seen:
                continue
            seen.add(p)
            fp = Path(p)
            vids.append({
                "path": str(fp),
                "filename": fp.name,
                "size_mb": round(fp.stat().st_size / (1024 * 1024), 2),
            })
    return vids


def resolve_media_path(filepath: str, output_dir: Path) -> Path | None:
    if filepath.startswith("home/"):
        filepath = "/" + filepath
    p = Path(filepath)
    if p.is_absolute() and p.exists():
        return p
    # Try CWD-relative first (engine uses relative artifact paths)
    cwd_resolved = Path.cwd() / p
    if cwd_resolved.exists():
        return cwd_resolved
    candidates = [output_dir / filepath, Path.home() / filepath]
    for c in candidates:
        if c.exists():
            return c
    # fallback: search by basename
    for found in output_dir.rglob(p.name):
        return found
    return None


def serve_media(filepath: str, output_dir: Path) -> Any:
    resolved = resolve_media_path(filepath, output_dir)
    if not resolved:
        return jsonify({"error": "file not found"}), 404
    mime = _MIME.get(resolved.suffix.lower(), "application/octet-stream")
    return send_file(str(resolved), mimetype=mime)


def extract_thumbnail(filepath: str, output_dir: Path) -> Any:
    resolved = resolve_media_path(filepath, output_dir)
    if not resolved:
        return jsonify({"error": "file not found"}), 404
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(  # noqa: S603
            ["ffmpeg", "-i", str(resolved), "-frames:v", "1", tmp_path, "-y", "-loglevel", "quiet"],
            timeout=10, capture_output=True,
        )
        if Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 0:
            return send_file(tmp_path, mimetype="image/png")
        return jsonify({"error": "thumbnail extraction failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def browse_dir(directory: str) -> Any:
    target = Path(os.path.expanduser(directory or "~"))
    if not target.is_dir():
        return jsonify({"error": "not a directory"}), 400
    entries: list[dict[str, Any]] = [
        {"name": "..", "path": str(target.parent), "type": "dir"},
    ]
    img_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    try:
        for item in sorted(target.iterdir()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                entries.append({"name": item.name + "/", "path": str(item), "type": "dir"})
            elif item.suffix.lower() in img_exts:
                entries.append({
                    "name": item.name, "path": str(item), "type": "image",
                    "size_kb": round(item.stat().st_size / 1024, 1),
                })
    except PermissionError:
        return jsonify({"error": "permission denied"}), 403
    return jsonify({"dir": str(target), "entries": entries})


def parse_stats(stats_file: Path, stem: str | None = None) -> dict[str, Any]:
    if not stats_file.exists():
        return {"total": 0, "success": 0, "fail": 0, "attempts": []}
    records = []
    for line in stats_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if stem:
        records = [r for r in records if r.get("image", "") == stem]
    total = len(records)
    success = sum(1 for r in records if r.get("result") == "success")
    issue_counts: dict[str, int] = {}
    for r in records:
        for issue in r.get("issues", []):
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    return {
        "total": total,
        "success": success,
        "fail": total - success,
        "success_rate": round(success / total * 100, 1) if total else 0,
        "issue_counts": issue_counts,
        "attempts": records,
    }


def get_comfyui_progress() -> dict[str, Any] | None:
    try:
        from discoverex.adapters.outbound.models.comfyui_client import ComfyUIClient

        p = ComfyUIClient.current_progress
        if p["total"] > 0:
            return {"step": p["step"], "total": p["total"], "percent": round(p["step"] / p["total"] * 100)}
    except Exception:
        pass
    return None


def build_keyframe_only_lottie(
    img: Path, stem: str, motion_dir: Path, converter: Any,
) -> dict[str, Any] | None:
    try:
        from PIL import Image
        out_dir = motion_dir / f"{stem}_transparent"
        out_dir.mkdir(parents=True, exist_ok=True)
        frame = out_dir / f"{stem}_frame_0000.png"
        pil = Image.open(img).convert("RGBA")
        pil.save(frame, "PNG")
        result = converter.convert([frame], preset="original", fps=1)
        lp = result.lottie_path
        if lp and Path(str(lp)).exists():
            lp_path = Path(str(lp))
            lj = json.loads(lp_path.read_text(encoding="utf-8"))
            ow, oh = pil.size
            sz = round(lp_path.stat().st_size / (1024 * 1024), 1)
            return {"lottie_path": str(lp), "lottie_info": {
                "fps": 1, "frame_count": 1, "duration_ms": 1000,
                "width": lj.get("w", 480), "height": lj.get("h", 480),
                "original_width": ow, "original_height": oh,
                "file_size_mb": sz}}
    except Exception as e:
        logger.warning("[Classify] keyframe-only lottie failed: %s", e)
    return None


def resolve_lottie(raw: str, output_dir: Path) -> Path | None:
    p = Path(raw)
    if p.is_absolute() and p.exists():
        return p
    cwd = Path.cwd() / raw
    if cwd.exists():
        return cwd
    od = output_dir / raw
    if od.exists():
        return od
    logger.warning("[export] lottie not found: raw=%s cwd=%s od=%s", raw, cwd, od)
    return None
