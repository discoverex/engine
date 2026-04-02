"""ComfyUI WebSocket progress listener — real-time step/total tracking."""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


def start_ws_progress(
    base_url: str, stop_flag: dict[str, bool],
    progress_ref: dict[str, int],
) -> threading.Thread:
    """Connect to ComfyUI WebSocket and update progress_ref in real-time."""
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")

    def _listen() -> None:
        try:
            from websockets.sync.client import connect  # type: ignore[import-untyped]

            with connect(f"{ws_url}/ws?clientId=progress") as ws:
                while not stop_flag.get("stop"):
                    try:
                        msg = ws.recv(timeout=2)
                        data: dict[str, Any] = json.loads(msg)
                        if data.get("type") == "progress":
                            d = data["data"]
                            progress_ref["step"] = d["value"]
                            progress_ref["total"] = d["max"]
                        elif (data.get("type") == "executing"
                              and data.get("data", {}).get("node") is None):
                            break
                    except TimeoutError:
                        continue
                    except Exception:
                        break
        except Exception as e:
            logger.debug("[ComfyUI] ws progress error: %s", e)

    t = threading.Thread(target=_listen, daemon=True)
    t.start()
    return t
