from __future__ import annotations

import pytest

from discoverex.adapters.outbound.models.hidden_object_backends import BackendRuntime
from discoverex.adapters.outbound.models.runtime import (
    RuntimeResolution,
    validate_diffusers_runtime,
)


class _TransformersV5:
    __version__ = "5.2.0"
    T5Tokenizer = object()


def test_validate_diffusers_runtime_allows_transformers_v5_with_t5_support() -> None:
    runtime = RuntimeResolution(
        available=True,
        torch=object(),
        transformers=_TransformersV5(),
        reason="",
    )

    validate_diffusers_runtime(runtime)


class _TransformersBroken:
    __version__ = "5.2.0"


def test_validate_diffusers_runtime_rejects_missing_t5_support() -> None:
    runtime = RuntimeResolution(
        available=True,
        torch=object(),
        transformers=_TransformersBroken(),
        reason="",
    )

    with pytest.raises(RuntimeError, match="transformers=5.2.0"):
        validate_diffusers_runtime(runtime)


def test_validate_diffusers_runtime_allows_hidden_object_backend_runtime() -> None:
    runtime = BackendRuntime(
        device="cuda",
        dtype="float16",
        offload_mode="sequential",
        enable_attention_slicing=True,
        enable_vae_slicing=True,
        enable_vae_tiling=True,
        enable_xformers_memory_efficient_attention=True,
        enable_fp8_layerwise_casting=False,
        enable_channels_last=True,
    )

    validate_diffusers_runtime(runtime)
