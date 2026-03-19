from __future__ import annotations

from pathlib import Path
from typing import Any


def build_execution_snapshot(**kwargs: Any) -> dict[str, Any]:
    from discoverex.execution_snapshot import build_execution_snapshot as _build

    return _build(**kwargs)


def summarize_for_logging(snapshot: dict[str, Any]) -> dict[str, str]:
    from discoverex.execution_snapshot import summarize_for_logging as _summarize

    return _summarize(snapshot)


def write_execution_snapshot(**kwargs: Any) -> Path:
    from discoverex.execution_snapshot import write_execution_snapshot as _write

    return _write(**kwargs)
