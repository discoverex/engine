from __future__ import annotations

import base64
from pathlib import Path

# Minimal valid 8x8 PNG for pipeline artifact checks.
_MINIMAL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGOs2GLDgA0wYRUd"
    "tBIAHcMBeOJ8wPUAAAAASUVORK5CYII="
)


def ensure_output_image(output_path: str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(base64.b64decode(_MINIMAL_PNG_BASE64))
    return path
