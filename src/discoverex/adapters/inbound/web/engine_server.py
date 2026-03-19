"""Engine animate dashboard — Flask REST API wrapping engine ports.

Drop-in replacement for sprite_gen's wan_server.py.
Serves wan_dashboard.html and routes API calls through engine adapters.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request
from flask_cors import CORS  # type: ignore[import-untyped]

from discoverex.domain.animate_keyframe import KeyframeConfig

from .engine_server_helpers import video_list

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(os.environ.get("WAN_OUTPUT_DIR", "artifacts/animate"))
DIR_MOTION = OUTPUT_DIR / "motion"
DASHBOARD_PATH = Path(
    os.environ.get(
        "DASHBOARD_HTML",
        os.path.expanduser(
            "~/anim_pipeline/image_pipeline/sprite_gen/wan_dashboard.html"
        ),
    )
)

_app = Flask(__name__)
CORS(_app)
_orchestrator: Any = None
_jobs: dict[str, dict[str, Any]] = {}


def create_app(orchestrator: Any) -> Flask:
    """Initialize Flask app with engine orchestrator."""
    global _orchestrator  # noqa: PLW0603
    _orchestrator = orchestrator
    DIR_MOTION.mkdir(parents=True, exist_ok=True)

    from .engine_server_extra import register_extra_routes

    register_extra_routes(_app, orchestrator, OUTPUT_DIR)
    return _app


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------


@_app.route("/")
def index() -> Response | tuple[str, int]:
    if DASHBOARD_PATH.exists():
        return Response(DASHBOARD_PATH.read_text(encoding="utf-8"), content_type="text/html")
    return "dashboard not found", 404


# ------------------------------------------------------------------
# Stage 1 — Classification
# ------------------------------------------------------------------


@_app.route("/api/classify", methods=["POST"])
def api_classify() -> Any:
    data = request.get_json(force=True)
    image_path = data.get("image_path", "")
    if not image_path or not Path(image_path).exists():
        return jsonify({"error": "image_path required"}), 400

    img = Path(image_path)
    mode = _orchestrator.mode_classifier.classify(img)
    stem = img.stem

    existing = video_list(DIR_MOTION, stem)
    resp: dict[str, Any] = {
        "processing_mode": mode.processing_mode.value,
        "facing_direction": mode.facing_direction.value,
        "has_deformable": mode.has_deformable,
        "is_scene": mode.is_scene,
        "subject_desc": mode.subject_desc,
        "suggested_action": mode.suggested_action,
        "reason": mode.reason,
        "existing_videos": existing,
        "keyframe_config": None,
        "lottie_path": None,
        "combined_lottie_path": None,
        "lottie_info": None,
    }

    if mode.processing_mode.value == "keyframe_only":
        try:
            kf = _orchestrator.keyframe_generator.generate(
                KeyframeConfig(
                    suggested_action=mode.suggested_action,
                    facing_direction=mode.facing_direction.value,
                )
            )
            resp["keyframe_config"] = kf.model_dump()
        except Exception as e:
            logger.warning("[Classify] keyframe generation failed: %s", e)

    return jsonify(resp)


# ------------------------------------------------------------------
# Stage 2 — Async Motion Generation
# ------------------------------------------------------------------


@_app.route("/api/generate", methods=["POST"])
def api_generate() -> Any:
    data = request.get_json(force=True)
    image_path = data.get("image_path", "")
    if not image_path or not Path(image_path).exists():
        return jsonify({"error": "image_path required"}), 400

    max_retries = int(data.get("max_retries", 7))
    job_id = uuid.uuid4().hex[:8]
    stem = Path(image_path).stem

    _jobs[job_id] = {
        "status": "running",
        "stem": stem,
        "started_at": time.time(),
        "result": None,
        "error": None,
    }

    def _run() -> None:
        try:
            result = _orchestrator.run(Path(image_path))
            _jobs[job_id]["result"] = {
                "success": result.success,
                "video_path": str(result.video_path) if result.video_path else None,
                "attempts": result.attempts,
            }
            _jobs[job_id]["status"] = "done"
        except Exception as e:
            _jobs[job_id]["error"] = str(e)
            _jobs[job_id]["status"] = "error"

    # Override max_retries via orchestrator
    _orchestrator.max_retries = max_retries
    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "status": "running", "max_retries": max_retries})


@_app.route("/api/status/<job_id>")
def api_status(job_id: str) -> Any:
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    elapsed = int(time.time() - job["started_at"])
    videos = video_list(DIR_MOTION, job["stem"])
    return jsonify({
        "status": job["status"],
        "elapsed_sec": elapsed,
        "result": job.get("result"),
        "error": job.get("error"),
        "videos": videos,
    })


# ------------------------------------------------------------------
# Stage 3 — Video listing
# ------------------------------------------------------------------


@_app.route("/api/videos/<stem>")
def api_videos(stem: str) -> Any:
    return jsonify({"stem": stem, "videos": video_list(DIR_MOTION, stem)})


@_app.route("/api/videos_all")
def api_videos_all() -> Any:
    vids = video_list(DIR_MOTION, "*")
    return jsonify({"total": len(vids), "videos": vids})
