from __future__ import annotations

from types import SimpleNamespace

from discoverex.adapters.outbound.models.pipeline_memory import (
    configure_diffusers_pipeline,
)


class _FakeModule:
    def __init__(self) -> None:
        self.layerwise_calls: list[tuple[object, object]] = []
        self.memory_format = None

    def enable_layerwise_casting(
        self, *, storage_dtype: object, compute_dtype: object
    ) -> None:
        self.layerwise_calls.append((storage_dtype, compute_dtype))

    def to(self, *, memory_format: object) -> None:
        self.memory_format = memory_format


class _FakePipe:
    def __init__(self) -> None:
        self.unet = _FakeModule()
        self.vae = _FakeModule()
        self.text_encoder = _FakeModule()
        self.progress_bar_disabled = None
        self.attention_slicing = None
        self.vae_slicing_enabled = False
        self.vae_tiling_enabled = False
        self.xformers_enabled = False
        self.offload_mode = None
        self.sent_to_device = None

    def set_progress_bar_config(self, *, disable: bool) -> None:
        self.progress_bar_disabled = disable

    def enable_attention_slicing(self, value: str) -> None:
        self.attention_slicing = value

    def enable_vae_slicing(self) -> None:
        self.vae_slicing_enabled = True

    def enable_vae_tiling(self) -> None:
        self.vae_tiling_enabled = True

    def enable_xformers_memory_efficient_attention(self) -> None:
        self.xformers_enabled = True

    def enable_model_cpu_offload(self) -> None:
        self.offload_mode = "model"

    def enable_sequential_cpu_offload(self) -> None:
        self.offload_mode = "sequential"

    def to(self, device: str) -> "_FakePipe":
        self.sent_to_device = device
        return self


class _FakeTorch:
    float8_e4m3fn = object()
    float16 = object()
    float32 = object()
    channels_last = object()


def test_configure_diffusers_pipeline_enables_low_vram_features(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pipe = _FakePipe()
    handle = SimpleNamespace(device="cuda", dtype="float16")
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.pipeline_memory._load_torch",
        lambda: _FakeTorch,
    )

    configured = configure_diffusers_pipeline(
        pipe,
        handle=handle,
        offload_mode="model",
        enable_attention_slicing=True,
        enable_vae_slicing=True,
        enable_vae_tiling=True,
        enable_xformers_memory_efficient_attention=True,
        enable_fp8_layerwise_casting=True,
        enable_channels_last=True,
    )

    assert configured is pipe
    assert pipe.progress_bar_disabled is False
    assert pipe.attention_slicing == "auto"
    assert pipe.vae_slicing_enabled is True
    assert pipe.vae_tiling_enabled is True
    assert pipe.xformers_enabled is True
    assert pipe.offload_mode == "model"
    assert pipe.sent_to_device is None
    assert pipe.unet.layerwise_calls
    assert pipe.vae.layerwise_calls
    assert pipe.unet.memory_format is _FakeTorch.channels_last
