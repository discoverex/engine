"""ComfyUI workflow loading and parameter injection.

Loads a workflow JSON (GUI or API format), converts if needed,
and injects runtime parameters (prompts, seed, image, etc.).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_and_inject(
    workflow_path: Path,
    image_filename: str,
    positive: str,
    negative: str,
    frame_rate: int,
    seed: int,
    steps: int = 20,
    pingpong: bool = False,
    width: int = 480,
    height: int = 480,
    positive_node_id: str | None = None,
    negative_node_id: str | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    """Load workflow JSON and inject runtime parameters."""
    raw = json.loads(workflow_path.read_text(encoding="utf-8"))

    if isinstance(raw, dict) and "nodes" in raw:
        logger.info("[Workflow] GUI format detected -> converting to API format")
        workflow = _gui_to_api(raw)
    else:
        workflow = raw

    # --- CLIPTextEncode: positive / negative prompts ---
    clip_nodes = sorted(
        (
            nid
            for nid, n in workflow.items()
            if isinstance(n, dict) and n.get("class_type") == "CLIPTextEncode"
        ),
        key=lambda x: int(x) if x.isdigit() else 0,
    )
    if len(clip_nodes) < 2:  # noqa: PLR2004
        msg = f"need 2 CLIPTextEncode nodes, found: {clip_nodes}"
        raise ValueError(msg)

    pos_id = positive_node_id or clip_nodes[0]
    neg_id = negative_node_id or clip_nodes[1]
    workflow[pos_id]["inputs"]["text"] = positive
    workflow[neg_id]["inputs"]["text"] = negative

    # --- Iterate nodes and inject by class_type ---
    for _nid, node in workflow.items():
        if not isinstance(node, dict):
            continue
        ctype = node.get("class_type", "")
        if ctype == "KSampler":
            node["inputs"]["seed"] = seed
            node["inputs"]["control_after_generate"] = "fixed"
            node["inputs"]["steps"] = steps
        elif ctype == "VHS_VideoCombine":
            node["inputs"]["frame_rate"] = frame_rate
            node["inputs"]["pingpong"] = pingpong
        elif ctype == "LoadImage":
            node["inputs"]["image"] = image_filename
        elif ctype in ("WanImageToVideo", "Wan22ImageToVideoLatent"):
            node["inputs"]["width"] = width
            node["inputs"]["height"] = height
        elif ctype == "UnetLoaderGGUF" and model_name:
            node["inputs"]["unet_name"] = model_name

    model_log = f" model={model_name}" if model_name else ""
    logger.info(
        "[Workflow] injected: seed=%d steps=%d fps=%d %dx%d%s",
        seed, steps, frame_rate, width, height, model_log,
    )
    return workflow


# ------------------------------------------------------------------
# GUI format -> API format conversion
# ------------------------------------------------------------------

_WIDGET_KEYS: dict[str, list[str]] = {
    "CLIPLoader": ["clip_name", "type", "device"],
    "CLIPLoaderGGUF": ["clip_name", "type"],
    "CLIPVisionLoader": ["clip_name"],
    "VAELoader": ["vae_name"],
    "UnetLoaderGGUF": ["unet_name"],
    "CLIPTextEncode": ["text"],
    "CLIPVisionEncode": ["crop"],
    "WanImageToVideo": ["width", "height", "length", "batch_size"],
    "Wan22ImageToVideoLatent": ["width", "height", "length", "batch_size"],
    "KSampler": [
        "seed", "control_after_generate", "steps", "cfg",
        "sampler_name", "scheduler", "denoise",
    ],
    "LoadImage": ["image", "upload"],
    "VAEDecode": [],
    "VHS_VideoCombine": [],
}


def _gui_to_api(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert ComfyUI GUI save format to API format."""
    link_by_id: dict[int, list[Any]] = {}
    for lk in raw.get("links", []):
        link_by_id[lk[0]] = [str(lk[1]), lk[2]]

    api_workflow: dict[str, Any] = {}
    for node in raw["nodes"]:
        node_id = str(node["id"])
        ntype: str = node["type"]
        wv = node.get("widgets_values", [])
        ninputs = node.get("inputs", [])

        inputs: dict[str, Any] = {}

        if ntype == "VHS_VideoCombine" and isinstance(wv, dict):
            for k, v in wv.items():
                if k != "videopreview":
                    inputs[k] = v
            inputs["save_output"] = True
            inputs["loop_count"] = 0
        else:
            for i, key in enumerate(_WIDGET_KEYS.get(ntype, [])):
                if i < len(wv):
                    inputs[key] = wv[i]

        for inp in ninputs:
            link_id = inp.get("link")
            if link_id is None:
                continue
            src = link_by_id.get(link_id)
            if src:
                inputs[inp["name"]] = src

        api_workflow[node_id] = {"class_type": ntype, "inputs": inputs}

    return api_workflow
