from __future__ import annotations

import gc
from typing import Any

from discoverex.adapters.outbound.models.runtime_cleanup import clear_model_runtime
from discoverex.runtime_logging import get_logger

logger = get_logger("discoverex.model_lifecycle")


def _stdout_debug(message: str) -> None:
    print(f"[discoverex-debug] {message}", flush=True)


def stage_gpu_barrier(stage_name: str) -> None:
    gc.collect()
    try:
        import torch  # type: ignore
    except Exception:
        logger.info("gpu barrier stage=%s torch_unavailable=true", stage_name)
        return
    if not torch.cuda.is_available():
        logger.info("gpu barrier stage=%s cuda_available=false", stage_name)
        return
    try:
        torch.cuda.synchronize()
    except Exception:
        pass
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    try:
        torch.cuda.ipc_collect()
    except Exception:
        pass
    try:
        torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass
    allocated_gb = float(torch.cuda.memory_allocated()) / float(1024 ** 3)
    reserved_gb = float(torch.cuda.memory_reserved()) / float(1024 ** 3)
    logger.info(
        "gpu barrier stage=%s allocated_gb=%.3f reserved_gb=%.3f",
        stage_name,
        allocated_gb,
        reserved_gb,
    )
    _stdout_debug(
        f"gpu_barrier stage={stage_name} allocated_gb={allocated_gb:.3f} reserved_gb={reserved_gb:.3f}"
    )


def unload_model(model: Any) -> None:
    unload = getattr(model, "unload", None)
    if callable(unload):
        unload()
    else:
        clear_model_runtime(model)
    stage_gpu_barrier(getattr(model, "__class__", type(model)).__name__)
