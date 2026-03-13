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


def parse_progress_event_line(line: str) -> dict[str, Any] | None:
    candidate = line.strip()
    if not candidate.startswith(PROGRESS_PREFIX + " "):
        return None
    payload = candidate.removeprefix(PROGRESS_PREFIX + " ").strip()
    if not payload:
        return None
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    return decoded
