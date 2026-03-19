from __future__ import annotations

from dataclasses import dataclass

from ..pipeline_memory import OffloadMode


@dataclass(frozen=True)
class BackendRuntime:
    device: str
    dtype: str
    offload_mode: OffloadMode
    enable_attention_slicing: bool
    enable_vae_slicing: bool
    enable_vae_tiling: bool
    enable_xformers_memory_efficient_attention: bool
    enable_fp8_layerwise_casting: bool
    enable_channels_last: bool


@dataclass(frozen=True)
class RuntimeHandle:
    runtime: BackendRuntime

    @property
    def device(self) -> str:
        return self.runtime.device

    @property
    def dtype(self) -> str:
        return self.runtime.dtype
