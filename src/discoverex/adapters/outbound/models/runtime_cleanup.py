from __future__ import annotations

import gc
from typing import Any


def clear_model_runtime(*components: Any) -> None:
    for component in components:
        if component is None:
            continue
        del component
    gc.collect()
    try:
        import torch  # type: ignore
    except Exception:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
