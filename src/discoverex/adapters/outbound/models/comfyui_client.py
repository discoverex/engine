"""ComfyUI HTTP API client — pure transport layer."""

from __future__ import annotations

import gc
import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOG_INTERVAL = 30  # seconds between progress log lines


class ComfyUIClient:
    """Stateless HTTP client for ComfyUI server."""

    # Shared progress state — updated during polling, read by engine_server.
    current_progress: dict[str, int] = {"step": 0, "total": 0}

    def __init__(
        self,
        base_url: str,
        timeout_upload: int = 30,
        timeout_poll: int = 1800,
        poll_interval: float = 2.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_upload = timeout_upload
        self._timeout_poll = timeout_poll
        self._poll_interval = poll_interval

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Check ComfyUI server reachability via /system_stats."""
        try:
            url = f"{self._base_url}/system_stats"
            urllib.request.urlopen(url, timeout=5)  # noqa: S310
            return True
        except Exception:
            return False

    def upload_image(self, image_path: Path) -> str:
        """Upload image to ComfyUI input folder. Returns uploaded filename."""
        filename = image_path.name
        data = image_path.read_bytes()

        boundary = "----EngineComfyUIBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + data + (
            f"\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
            f"true\r\n"
            f"--{boundary}--\r\n"
        ).encode()

        req = urllib.request.Request(
            f"{self._base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout_upload) as resp:  # noqa: S310
            result = json.loads(resp.read())

        uploaded_name: str = result.get("name", filename)
        logger.info("[ComfyUI] image uploaded: %s", uploaded_name)
        return uploaded_name

    def queue_prompt(self, workflow: dict[str, Any], client_id: str) -> str:
        """Queue workflow for execution. Returns prompt_id."""
        payload = json.dumps({"prompt": workflow, "client_id": client_id}).encode()
        req = urllib.request.Request(
            f"{self._base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout_upload) as resp:  # noqa: S310
            result = json.loads(resp.read())

        prompt_id: str = result["prompt_id"]
        logger.info("[ComfyUI] queued: prompt_id=%s", prompt_id)
        return prompt_id

    def wait_for_completion(self, prompt_id: str) -> dict[str, Any]:
        """Poll /history until generation completes. Returns history entry."""
        start = time.monotonic()
        last_log = 0.0

        while True:
            elapsed = time.monotonic() - start
            if elapsed > self._timeout_poll:
                raise TimeoutError(f"ComfyUI timeout ({self._timeout_poll}s)")

            url = f"{self._base_url}/history/{prompt_id}"
            with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310
                history = json.loads(resp.read())

            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("completed", False) or status.get(
                    "status_str", ""
                ) in ("success", "error", ""):
                    logger.info(
                        "[ComfyUI] generation complete (%.1fs)", elapsed,
                    )
                    return dict(entry)

            # Query /queue for running status + node progress
            self._update_progress(prompt_id)

            if elapsed - last_log >= _LOG_INTERVAL:
                p = ComfyUIClient.current_progress
                extra = f" ({p['step']}/{p['total']})" if p["total"] > 0 else ""
                logger.info("[ComfyUI] generating… %.0fs elapsed%s", elapsed, extra)
                last_log = elapsed

            time.sleep(self._poll_interval)

    def download_video(
        self, history: dict[str, Any], output_path: Path,
    ) -> Path:
        """Extract and download video from history outputs."""
        video_filename, subfolder = self._find_video(history)
        params = urllib.parse.urlencode(
            {"filename": video_filename, "subfolder": subfolder, "type": "output"},
        )
        url = f"{self._base_url}/view?{params}"
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
            video_data = resp.read()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video_data)
        logger.info("[ComfyUI] video downloaded: %s", output_path)
        return output_path

    def free_memory(self) -> None:
        """Release ComfyUI VRAM/RAM and run Python GC."""
        try:
            data = json.dumps(
                {"unload_models": True, "free_memory": True},
            ).encode()
            req = urllib.request.Request(
                f"{self._base_url}/free",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)  # noqa: S310
            gc.collect()
            try:
                import torch  # type: ignore[import-untyped]

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            logger.info("[ComfyUI] memory freed")
        except Exception as exc:
            logger.warning("[ComfyUI] free_memory failed (non-fatal): %s", exc)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _update_progress(self, prompt_id: str) -> None:
        """Poll /queue to estimate progress from running nodes."""
        try:
            with urllib.request.urlopen(f"{self._base_url}/queue", timeout=5) as r:  # noqa: S310
                qdata = json.loads(r.read())
            for item in qdata.get("queue_running", []):
                if len(item) > 1 and item[1] == prompt_id and len(item) > 3 and isinstance(item[3], dict):
                    done = len(item[3].get("outputs", {}))
                    total = len(item[2]) if len(item) > 2 and isinstance(item[2], dict) else 0
                    if total > 0:
                        ComfyUIClient.current_progress = {"step": done, "total": total}
        except Exception:
            pass

    @staticmethod
    def _find_video(history: dict[str, Any]) -> tuple[str, str]:
        for node_output in history.get("outputs", {}).values():
            for item in node_output.get("gifs", []):
                if item.get("filename", "").endswith(".mp4"):
                    return item["filename"], item.get("subfolder", "")
        raise ValueError("no .mp4 video found in ComfyUI history outputs")
