from __future__ import annotations

from typing import Any

from discoverex.adapters.outbound.models.runtime_cleanup import clear_model_runtime


def unload_model(model: Any) -> None:
    unload = getattr(model, "unload", None)
    if callable(unload):
        unload()
        return
    clear_model_runtime(model)
