from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from discoverex.execution_snapshot import update_execution_snapshot
from discoverex.runtime_logging import get_logger

logger = get_logger("discoverex.runtime.vram")


@contextmanager
def track_stage_vram(context: Any, stage: str) -> Iterator[None]:
    torch_mod = _load_torch()
    if torch_mod is not None and torch_mod.cuda.is_available():
        try:
            torch_mod.cuda.reset_peak_memory_stats()
        except Exception:
            pass
    try:
        yield
    finally:
        metrics = _read_vram_metrics(torch_mod)
        _record_stage_metrics(context, stage, metrics)
        logger.info("stage vram peak stage=%s metrics=%s", stage, json.dumps(metrics, sort_keys=True))


def _record_stage_metrics(context: Any, stage: str, metrics: dict[str, Any]) -> None:
    snapshot = getattr(context, "execution_snapshot", None)
    if not isinstance(snapshot, dict):
        return
    runtime_metrics = snapshot.setdefault("runtime_metrics", {})
    if not isinstance(runtime_metrics, dict):
        return
    vram_peaks = runtime_metrics.setdefault("vram_peaks", {})
    if not isinstance(vram_peaks, dict):
        return
    vram_peaks[stage] = metrics
    path = getattr(context, "execution_snapshot_path", None)
    if isinstance(path, Path):
        update_execution_snapshot(path, snapshot)


def _read_vram_metrics(torch_mod: Any | None) -> dict[str, Any]:
    if torch_mod is None or not torch_mod.cuda.is_available():
        return {"device": "cpu", "available": False}
    try:
        return {
            "device": "cuda",
            "available": True,
            "peak_allocated_bytes": int(torch_mod.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch_mod.cuda.max_memory_reserved()),
            "allocated_bytes": int(torch_mod.cuda.memory_allocated()),
            "reserved_bytes": int(torch_mod.cuda.memory_reserved()),
        }
    except Exception:
        return {"device": "cuda", "available": True, "error": "memory_query_failed"}


def _load_torch() -> Any | None:
    try:
        import torch  # type: ignore
    except Exception:
        return None
    return torch
