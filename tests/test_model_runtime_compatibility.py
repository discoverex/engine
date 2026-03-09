from __future__ import annotations

import pytest

from discoverex.adapters.outbound.models.runtime import (
    RuntimeResolution,
    validate_diffusers_runtime,
)


class _TransformersV5:
    __version__ = "5.2.0"


def test_validate_diffusers_runtime_rejects_transformers_v5() -> None:
    runtime = RuntimeResolution(
        available=True,
        torch=object(),
        transformers=_TransformersV5(),
        reason="",
    )

    with pytest.raises(RuntimeError, match="transformers=5.2.0"):
        validate_diffusers_runtime(runtime)
