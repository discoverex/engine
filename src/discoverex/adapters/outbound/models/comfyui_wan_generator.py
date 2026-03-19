"""ComfyUI WAN I2V generator — AnimationGenerationPort adapter.

Orchestrates ComfyUIClient and workflow injection to generate
WAN Image-to-Video animations via a running ComfyUI server.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from discoverex.domain.animate import AnimationGenerationParams
from discoverex.domain.animate_keyframe import AnimationResult
from discoverex.models.types import ModelHandle

from .comfyui_client import ComfyUIClient
from .comfyui_workflow import load_and_inject

logger = logging.getLogger(__name__)


class ComfyUIWanGenerator:
    """AnimationGenerationPort implementation via ComfyUI HTTP API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        workflow_path: str = "",
        steps: int = 20,
        width: int = 480,
        height: int = 480,
        timeout_upload: int = 30,
        timeout_poll: int = 1800,
        poll_interval: float = 2.0,
        positive_node_id: str | None = None,
        negative_node_id: str | None = None,
        free_between_attempts: bool = False,
    ) -> None:
        self._base_url = base_url
        self._workflow_path = Path(workflow_path)
        self._steps = steps
        self._width = width
        self._height = height
        self._timeout_upload = timeout_upload
        self._timeout_poll = timeout_poll
        self._poll_interval = poll_interval
        self._positive_node_id = positive_node_id
        self._negative_node_id = negative_node_id
        self._free_between_attempts = free_between_attempts
        self._client: ComfyUIClient | None = None
        self._client_id: str = ""

    # ------------------------------------------------------------------
    # Port lifecycle
    # ------------------------------------------------------------------

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        """Initialize client and validate ComfyUI server reachability."""
        self._client = ComfyUIClient(
            base_url=self._base_url,
            timeout_upload=self._timeout_upload,
            timeout_poll=self._timeout_poll,
            poll_interval=self._poll_interval,
        )
        self._client_id = f"engine_{random.randint(0, 99999):05d}"  # noqa: S311

        if not self._client.health_check():
            msg = f"ComfyUI server unreachable at {self._base_url}"
            raise ConnectionError(msg)

        if self._workflow_path.name and not self._workflow_path.exists():
            msg = f"workflow file not found: {self._workflow_path}"
            raise FileNotFoundError(msg)

        logger.info(
            "[ComfyUI] loaded: url=%s workflow=%s client_id=%s",
            self._base_url, self._workflow_path, self._client_id,
        )

    def generate(
        self,
        handle: ModelHandle,  # noqa: ARG002
        uploaded_image: str,
        params: AnimationGenerationParams,
    ) -> AnimationResult:
        """Upload image, run workflow, download video."""
        assert self._client is not None, "call load() before generate()"  # noqa: S101

        uploaded_name = self._client.upload_image(Path(uploaded_image))

        workflow = load_and_inject(
            workflow_path=self._workflow_path,
            image_filename=uploaded_name,
            positive=params.positive,
            negative=params.negative,
            frame_rate=params.frame_rate,
            seed=params.seed,
            steps=self._steps,
            pingpong=params.pingpong,
            width=self._width,
            height=self._height,
            positive_node_id=self._positive_node_id,
            negative_node_id=self._negative_node_id,
        )

        prompt_id = self._client.queue_prompt(workflow, self._client_id)
        history = self._client.wait_for_completion(prompt_id)

        output_path = Path(params.output_dir) / f"{params.stem}_a{params.attempt}.mp4"
        video_path = self._client.download_video(history, output_path)

        if self._free_between_attempts:
            self._client.free_memory()

        return AnimationResult(
            video_path=video_path, seed=params.seed, attempt=params.attempt,
        )

    def unload(self) -> None:
        """Release ComfyUI resources."""
        if self._client is not None:
            self._client.free_memory()
            self._client = None
        logger.info("[ComfyUI] unloaded")
