"""Extra API routes for engine dashboard — Stage 5, export, browse, stats.

Registered onto the Flask app via register_extra_routes().
"""

from __future__ import annotations

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
    serve_media,
)

logger = logging.getLogger(__name__)


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
        vid = Path(video_path)
        if not vid.exists():
            return jsonify({"error": "video_path not found"}), 400
        transparent = orchestrator.bg_remover.remove(vid, fps=fps)
        if not transparent or not transparent.frames:
            return jsonify({"error": "bg removal failed"}), 500
        converted = orchestrator.format_converter.convert(transparent.frames, preset, fps)
        return jsonify({
            "transparent_dir": str(transparent.frames[0].parent),
            "lottie_path": str(converted.lottie_path) if converted.lottie_path else None,
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

        lp = Path(lottie_path)
        if not lp.is_absolute():
            lp = output_dir / lottie_path
        if not lp.exists():
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
        lp = Path(lottie_path)
        if not lp.is_absolute():
            lp = output_dir / lottie_path
        if not lp.exists():
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

        comfyui_root = os.environ.get("COMFYUI_ROOT", os.path.expanduser("~/ComfyUI"))
        unet_dir = Path(comfyui_root) / "models" / "unet"
        installed = {Path(f).name for f in g.glob(str(unet_dir / "*.gguf"))}
        return jsonify({"installed": sorted(installed)})
