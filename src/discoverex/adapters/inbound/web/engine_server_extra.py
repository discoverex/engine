"""Extra API routes for engine dashboard — Stage 5, export, browse, stats."""

from __future__ import annotations

import json as _json
import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_file

from discoverex.adapters.outbound.animate.lottie_baker import bake_keyframes
from discoverex.domain.animate_keyframe import KeyframeConfig

from .engine_server_helpers import (
    browse_dir,
    extract_thumbnail,
    parse_stats,
    resolve_lottie,
    serve_media,
)

logger = logging.getLogger(__name__)


def _detect_original_size(video_path: Path) -> tuple[int, int]:
    """비디오 파일명에서 원본 이미지를 찾아 크기 반환."""
    from PIL import Image
    orig_stem = video_path.stem.rsplit("_a", 1)[0].replace("_processed", "")
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = video_path.parent / f"{orig_stem}{ext}"
        if p.exists():
            with Image.open(p) as img:
                return img.size
    return (480, 480)


def register_extra_routes(
    app: Flask, orchestrator: Any, output_dir: Path,
) -> None:
    """Register Stage 5, export, browse, stats, file-serving routes."""

    stats_file = output_dir / "validation_stats.txt"

    # --- Stage 4: BG Removal + Lottie ---

    @app.route("/api/select_video", methods=["POST"])
    def api_select_video() -> Any:
        data = request.get_json(force=True)
        video_path = data.get("video_path", "")
        preset = data.get("preset", "original")
        fps = int(data.get("fps", 16))
        target_size = data.get("target_size")
        vid = Path(video_path)
        if not vid.exists():
            return jsonify({"error": "video_path not found"}), 400

        orig_w, orig_h = _detect_original_size(vid)
        transparent = orchestrator.bg_remover.remove(vid, fps=fps)
        if not transparent or not transparent.frames:
            return jsonify({"error": "bg removal failed"}), 500
        effective_size = int(target_size) if target_size else max(orig_w, orig_h)
        converted = orchestrator.format_converter.convert_with_opts(
            transparent.frames, fps=fps, max_size=effective_size)
        lottie_info = None
        if converted.lottie_path and Path(str(converted.lottie_path)).exists():
            lp = Path(str(converted.lottie_path))
            with open(lp, encoding="utf-8") as _f:
                _lj = _json.load(_f)
            lottie_info = {
                "fps": fps,
                "frame_count": len(transparent.frames),
                "duration_ms": round(len(transparent.frames) / fps * 1000),
                "width": _lj.get("w", 0),
                "height": _lj.get("h", 0),
                "file_size_mb": round(lp.stat().st_size / (1024 * 1024), 1),
                "original_width": orig_w,
                "original_height": orig_h,
            }
        return jsonify({
            "transparent_dir": str(transparent.frames[0].parent),
            "lottie_path": str(converted.lottie_path) if converted.lottie_path else None,
            "lottie_info": lottie_info,
            "apng_path": str(converted.apng_path) if converted.apng_path else None,
            "webm_path": str(converted.webm_path) if converted.webm_path else None,
        })

    # --- Stage 5: Post-motion classification ---

    @app.route("/api/classify_motion", methods=["POST"])
    def api_classify_motion() -> Any:
        data = request.get_json(force=True)
        video_path = data.get("video_path", "")
        image_path = data.get("image_path", "")
        vid = Path(video_path)
        if not vid.exists():
            return jsonify({"error": "video_path required"}), 400
        img = Path(image_path) if image_path else vid
        result = orchestrator.post_motion_classifier.classify(vid, img)
        resp: dict[str, Any] = {
            "needs_keyframe": result.needs_keyframe,
            "travel_type": result.travel_type.value,
            "travel_direction": result.travel_direction.value,
            "confidence": result.confidence,
            "reason": result.reason,
            "suggested_keyframe": result.suggested_keyframe,
        }
        return jsonify(resp)

    # --- Keyframe generation ---

    @app.route("/api/generate_keyframe", methods=["POST"])
    def api_generate_keyframe() -> Any:
        data = request.get_json(force=True)
        action = data.get("suggested_action", "wobble")
        facing = data.get("facing_direction", "none")
        duration = data.get("duration_ms")
        config = KeyframeConfig(
            suggested_action=action,
            facing_direction=facing,
            duration_ms=duration,
        )
        kf = orchestrator.keyframe_generator.generate(config)
        return jsonify(kf.model_dump())

    # --- Export ---

    @app.route("/api/export_combined", methods=["POST"])
    def api_export_combined() -> Any:
        data = request.get_json(force=True)
        lottie_path = data.get("lottie_path", "")
        keyframe_data = data.get("keyframe_data", {})
        output_name = data.get("output_name", "")

        lp = resolve_lottie(lottie_path, output_dir)
        if not lp:
            return jsonify({"error": "lottie not found"}), 404
        if not keyframe_data or not keyframe_data.get("keyframes"):
            return jsonify({"error": "keyframe_data required"}), 400

        out_name = output_name or f"{lp.stem}_combined"
        out_path = lp.parent / f"{out_name}.json"
        try:
            bake_keyframes(str(lp), keyframe_data, str(out_path))
            return send_file(str(out_path), mimetype="application/json",
                             as_attachment=True, download_name=f"{out_name}.json")
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/export_lottie", methods=["POST"])
    def api_export_lottie() -> Any:
        data = request.get_json(force=True)
        lottie_path = data.get("lottie_path", "")
        lp = resolve_lottie(lottie_path, output_dir)
        if not lp:
            return jsonify({"error": "lottie not found"}), 404
        return send_file(str(lp), mimetype="application/json",
                         as_attachment=True, download_name=lp.name)

    # --- Stats ---

    @app.route("/api/stats/<stem>")
    def api_stats(stem: str) -> Any:
        result = parse_stats(stats_file, stem)
        result["stem"] = stem
        return jsonify(result)

    @app.route("/api/stats_all")
    def api_stats_all() -> Any:
        return jsonify(parse_stats(stats_file))

    # --- Browse ---

    @app.route("/api/browse")
    def api_browse() -> Any:
        return browse_dir(request.args.get("dir", "~"))

    # --- File serving ---

    @app.route("/api/files/<path:filepath>")
    def api_files(filepath: str) -> Any:
        return serve_media(filepath, output_dir)

    @app.route("/api/video_thumb/<path:filepath>")
    def api_video_thumb(filepath: str) -> Any:
        return extract_thumbnail(filepath, output_dir)

    # --- Available models ---

    @app.route("/api/available_models")
    def api_available_models() -> Any:
        import glob as g

        # VRAM estimates: (model_params, quant) → GB
        # 14B models (wan2.1-i2v-14b)
        _VRAM_14B: dict[str, float] = {
            "Q3_K_S": 6.5, "Q3_K_M": 7.0, "Q4_0": 8.3, "Q4_K_S": 8.75,
            "Q4_1": 9.2, "Q4_K_M": 9.65, "Q5_K_S": 10.1, "Q5_0": 10.3,
            "Q5_K_M": 10.6, "Q5_1": 11.0, "Q6_K": 11.8, "Q8_0": 15.0,
        }
        comfyui_root = os.environ.get("COMFYUI_ROOT", os.path.expanduser("~/ComfyUI"))
        unet_dir = Path(comfyui_root) / "models" / "unet"
        models = []
        for fp in sorted(Path(f) for f in g.glob(str(unet_dir / "*.gguf"))):
            name = fp.name
            size_gb = round(fp.stat().st_size / (1024**3), 1)
            quant = name.replace(".gguf", "").rsplit("-", 1)[-1]
            vram = _VRAM_14B.get(quant, size_gb)
            models.append({"name": name, "size_gb": size_gb, "vram_gb": vram})
        return jsonify({"models": models})
