from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class RuntimeResolution(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    available: bool
    torch: Any | None = None
    transformers: Any | None = None
    reason: str = ""


def resolve_runtime() -> RuntimeResolution:
    try:
        import torch  # type: ignore
        import transformers  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        return RuntimeResolution(available=False, reason=str(exc))
    return RuntimeResolution(available=True, torch=torch, transformers=transformers)


def validate_diffusers_runtime(runtime: RuntimeResolution | Any) -> None:
    runtime_available = getattr(runtime, "available", None)
    if runtime_available is None:
        # Hidden-object helper backends pass a lightweight runtime config that
        # only carries device/offload settings. In that case, skip the generic
        # availability contract check and let the actual backend import/load
        # path raise a more specific error if dependencies are missing.
        return
    if not runtime_available:
        raise RuntimeError(
            "torch/transformers runtime unavailable. "
            "Install with ml-gpu or ml-cpu extra."
        )
    transformers_mod = runtime.transformers
    version = str(getattr(transformers_mod, "__version__", "unknown"))
    has_t5_family = bool(
        getattr(transformers_mod, "MT5Tokenizer", None)
        or getattr(transformers_mod, "T5Tokenizer", None)
        or getattr(transformers_mod, "AutoTokenizer", None)
    )
    if not has_t5_family:
        raise RuntimeError(
            "incompatible diffusers runtime: installed transformers="
            f"{version}. Install a transformers build with T5 tokenizer support and rerun "
            "`uv sync --extra tracking --extra ml-cpu`."
        )


def normalize_dtype(dtype: str, torch_mod: Any | None) -> Any:
    if torch_mod is None:
        return dtype
    mapping = {
        "float16": getattr(torch_mod, "float16", None),
        "fp16": getattr(torch_mod, "float16", None),
        "bfloat16": getattr(torch_mod, "bfloat16", None),
        "bf16": getattr(torch_mod, "bfloat16", None),
        "float32": getattr(torch_mod, "float32", None),
        "fp32": getattr(torch_mod, "float32", None),
    }
    return mapping.get(dtype.lower()) or getattr(torch_mod, "float32", None)


def resolve_device(preferred_device: str, torch_mod: Any | None) -> str:
    if torch_mod is None:
        return preferred_device
    if preferred_device.startswith("cuda") and not torch_mod.cuda.is_available():
        return "cpu"
    return preferred_device


def apply_seed(seed: int | None, torch_mod: Any | None) -> None:
    if seed is None or torch_mod is None:
        return
    torch_mod.manual_seed(seed)
    if torch_mod.cuda.is_available():
        torch_mod.cuda.manual_seed_all(seed)


def build_runtime_extra(
    *,
    runtime: RuntimeResolution,
    requested_device: str,
    selected_device: str,
    requested_dtype: str,
    selected_dtype: str,
    precision: str,
    batch_size: int,
    seed: int | None,
) -> dict[str, Any]:
    fallback_used = (not runtime.available) or (requested_device != selected_device)
    fallback_reason = ""
    if not runtime.available:
        fallback_reason = runtime.reason
    elif requested_device != selected_device:
        fallback_reason = f"requested device '{requested_device}' is unavailable"

    return {
        "runtime_available": runtime.available,
        "runtime_reason": runtime.reason,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "requested_device": requested_device,
        "selected_device": selected_device,
        "requested_dtype": requested_dtype,
        "selected_dtype": selected_dtype,
        "precision": precision,
        "batch_size": batch_size,
        "seed": seed,
    }
