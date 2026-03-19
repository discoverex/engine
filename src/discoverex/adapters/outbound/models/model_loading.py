from __future__ import annotations

from typing import Any


def load_state_dict_materialized(module: Any, state_dict: dict[str, Any], *, strict: bool = True) -> Any:
    try:
        result = module.load_state_dict(state_dict, strict=strict, assign=True)
    except TypeError:
        result = module.load_state_dict(state_dict, strict=strict)
    _raise_if_meta_parameters(module)
    return result


def _raise_if_meta_parameters(module: Any) -> None:
    for name, param in module.named_parameters(recurse=True):
        if bool(getattr(param, "is_meta", False)):
            raise RuntimeError(
                f"parameter remained on meta device after weight loading: {name}"
            )
    for name, buffer in module.named_buffers(recurse=True):
        if bool(getattr(buffer, "is_meta", False)):
            raise RuntimeError(
                f"buffer remained on meta device after weight loading: {name}"
            )
