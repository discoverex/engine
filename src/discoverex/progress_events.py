from __future__ import annotations

import json
import sys
from typing import Any

PROGRESS_PREFIX = "[discoverex-progress]"


def emit_progress_event(
    *,
    stage: str,
    status: str,
    **fields: object,
) -> None:
    payload: dict[str, Any] = {
        "event": "stage",
        "stage": stage,
        "status": status,
    }
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = value
    print(
        f"{PROGRESS_PREFIX} {json.dumps(payload, ensure_ascii=True, sort_keys=True)}",
        file=sys.stderr,
        flush=True,
    )

