from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "build_inline_job_spec",
    "engine_entry_flow",
    "run_prefect_engine_entry_flow",
    "run_engine_entry",
    "run_engine_job",
]


def __getattr__(name: str) -> Any:
    if name in {
        "engine_entry_flow",
        "run_prefect_engine_entry_flow",
        "run_engine_entry",
    }:
        module = importlib.import_module("discoverex.application.flows.engine_entry")
        return getattr(module, name)
    if name in {"build_inline_job_spec", "run_engine_job"}:
        module = importlib.import_module("discoverex.application.flows.run_engine_job")
        return getattr(module, name)
    raise AttributeError(name)
