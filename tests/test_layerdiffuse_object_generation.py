from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from discoverex.adapters.outbound.models.layerdiffuse_object_generation import (
    LayerDiffuseObjectGenerationModel,
)
from discoverex.adapters.outbound.models.objects.layerdiffuse.generate import (
    _sample_latents,
    _to_rgba_image,
    generate_rgba,
)
from discoverex.adapters.outbound.models.objects.layerdiffuse.load import (
    _configure_scheduler,
)
from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.models.types import FxRequest


def test_layerdiffuse_object_generator_writes_rgba_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = LayerDiffuseObjectGenerationModel(strict_runtime=True)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.layerdiffuse_object_generation.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat",
                (),
                {"__version__": "4.46.0", "MT5Tokenizer": object()},
            )(),
            reason="",
        ),
    )
    monkeypatch.setattr(
        model,
        "_generate_rgba",
        lambda **_kwargs: Image.new("RGBA", (512, 512), color=(10, 20, 30, 200)),
    )
    handle = model.load("layerdiffuse-v1")
    output_path = tmp_path / "object.png"
    prediction = model.predict(
        handle,
        FxRequest(
            mode="object_generation",
            params={
                "output_path": str(output_path),
                "width": 512,
                "height": 512,
                "prompt": "hidden key",
            },
        ),
    )

    assert prediction["output_path"] == str(output_path)
    assert output_path.exists()
    assert Image.open(output_path).mode == "RGBA"


def test_generate_rgba_precomputes_prompt_embeds_and_offloads_text_encoders() -> None:
    class _FakeGenerator:
        def manual_seed(self, seed: int) -> "_FakeGenerator":
            return self

    fake_torch = SimpleNamespace(
        Generator=lambda device="cpu": _FakeGenerator(),
        cuda=SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None),
    )
    original_torch = sys.modules.get("torch")
    sys.modules["torch"] = fake_torch

    class _FakeEncoder:
        def __init__(self) -> None:
            self.moves: list[str] = []

        def to(self, device: str) -> "_FakeEncoder":
            self.moves.append(device)
            return self

    class _FakeVAE:
        dtype = "float16"

        class _Cfg:
            scaling_factor = 1.0

        config = _Cfg()

        def __init__(self) -> None:
            self.moves: list[tuple[str, str]] = []

        def to(self, *args: object, **kwargs: object) -> "_FakeVAE":
            if "device" in kwargs and "dtype" in kwargs:
                self.moves.append((str(kwargs["device"]), str(kwargs["dtype"])))
            elif args:
                self.moves.append((str(args[0]), self.dtype))
            return self

        def decode(self, latents: object, return_dict: bool = False) -> tuple[list[Image.Image]]:
            return ([Image.new("RGBA", (384, 384), color=(0, 0, 0, 255))],)

    class _FakePipe:
        def __init__(self) -> None:
            self._execution_device = "cuda"
            self.text_encoder = _FakeEncoder()
            self.text_encoder_2 = _FakeEncoder()
            self.vae = _FakeVAE()
            self.encode_calls: list[dict[str, object]] = []
            self.pipe_calls: list[dict[str, object]] = []

        def encode_prompt(self, **kwargs: object) -> tuple[str, str, str, str]:
            self.encode_calls.append(kwargs)
            return ("prompt", "negative", "pooled", "negative_pooled")

        def __call__(self, **kwargs: object) -> object:
            self.pipe_calls.append(kwargs)
            return ("latents",)

    pipe = _FakePipe()
    model = type(
        "_Model",
        (),
        {
            "_load_pipeline": staticmethod(lambda handle: pipe),
            "_load_transparent_decoder": staticmethod(lambda handle: None),
        },
    )()
    handle = type("_Handle", (), {"device": "cuda"})()

    try:
        image = generate_rgba(
            model=model,
            handle=handle,
            prompt="object",
            negative_prompt="bad",
            width=384,
            height=384,
            seed=None,
            num_inference_steps=3,
            guidance_scale=5.0,
        )
    finally:
        if original_torch is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = original_torch

    assert image.mode == "RGBA"
    assert pipe.encode_calls
    assert pipe.text_encoder.moves == ["cuda", "cpu"]
    assert pipe.text_encoder_2.moves == ["cuda", "cpu"]
    assert pipe.pipe_calls[0]["prompt"] is None
    assert pipe.pipe_calls[0]["negative_prompt"] is None
    assert pipe.pipe_calls[0]["num_images_per_prompt"] == 1
    assert pipe.pipe_calls[0]["prompt_embeds"] == "prompt"
    assert ("cpu", "float16") in pipe.vae.moves


def test_generate_rgba_moves_text_encoders_to_execution_device_before_encoding() -> None:
    class _FakeGenerator:
        def manual_seed(self, seed: int) -> "_FakeGenerator":
            return self

    fake_torch = SimpleNamespace(
        Generator=lambda device="cpu": _FakeGenerator(),
        cuda=SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None),
    )
    original_torch = sys.modules.get("torch")
    sys.modules["torch"] = fake_torch

    class _FakeEncoder:
        def __init__(self) -> None:
            self.moves: list[str] = []

        def to(self, device: str) -> "_FakeEncoder":
            self.moves.append(device)
            return self

    class _FakeVAE:
        dtype = "float16"

        class _Cfg:
            scaling_factor = 1.0

        config = _Cfg()

        def to(self, *args: object, **kwargs: object) -> "_FakeVAE":
            return self

        def decode(self, latents: object, return_dict: bool = False) -> tuple[list[Image.Image]]:
            return ([Image.new("RGBA", (384, 384), color=(0, 0, 0, 255))],)

    class _FakePipe:
        def __init__(self) -> None:
            self._execution_device = "cuda:0"
            self.text_encoder = _FakeEncoder()
            self.text_encoder_2 = _FakeEncoder()
            self.vae = _FakeVAE()

        def encode_prompt(self, **kwargs: object) -> tuple[str, str, str, str]:
            return ("prompt", "negative", "pooled", "negative_pooled")

        def __call__(self, **kwargs: object) -> object:
            return ("latents",)

    pipe = _FakePipe()
    model = type(
        "_Model",
        (),
        {
            "_load_pipeline": staticmethod(lambda handle: pipe),
            "_load_transparent_decoder": staticmethod(lambda handle: None),
        },
    )()
    handle = type("_Handle", (), {"device": "cuda:0"})()

    try:
        generate_rgba(
            model=model,
            handle=handle,
            prompt="object",
            negative_prompt="bad",
            width=384,
            height=384,
            seed=None,
            num_inference_steps=3,
            guidance_scale=5.0,
        )
    finally:
        if original_torch is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = original_torch

    assert pipe.text_encoder.moves[0] == "cuda:0"
    assert pipe.text_encoder_2.moves[0] == "cuda:0"


def test_generate_rgba_fails_when_vram_limit_is_exceeded() -> None:
    class _FakeGenerator:
        def manual_seed(self, seed: int) -> "_FakeGenerator":
            return self

    eight_gb = 8 * 1024 * 1024 * 1024
    fake_torch = SimpleNamespace(
        Generator=lambda device="cpu": _FakeGenerator(),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            empty_cache=lambda: None,
            max_memory_reserved=lambda: eight_gb,
        ),
    )
    original_torch = sys.modules.get("torch")
    sys.modules["torch"] = fake_torch

    class _FakeEncoder:
        def to(self, device: str) -> "_FakeEncoder":
            return self

    class _FakeVAE:
        dtype = "float16"

        class _Cfg:
            scaling_factor = 1.0

        config = _Cfg()

        def to(self, *args: object, **kwargs: object) -> "_FakeVAE":
            return self

    class _FakePipe:
        def __init__(self) -> None:
            self._execution_device = "cuda"
            self.text_encoder = _FakeEncoder()
            self.text_encoder_2 = _FakeEncoder()
            self.vae = _FakeVAE()

        def encode_prompt(self, **kwargs: object) -> tuple[str, str, str, str]:
            return ("prompt", "negative", "pooled", "negative_pooled")

        def __call__(self, **kwargs: object) -> object:
            raise AssertionError("pipeline should fail before inference")

    pipe = _FakePipe()
    model = type(
        "_Model",
        (),
        {
            "_load_pipeline": staticmethod(lambda handle: pipe),
            "_load_transparent_decoder": staticmethod(lambda handle: object()),
        },
    )()
    handle = type("_Handle", (), {"device": "cuda"})()

    try:
        with pytest.raises(RuntimeError, match="exceeded vram limit"):
            generate_rgba(
                model=model,
                handle=handle,
                prompt="object",
                negative_prompt="bad",
                width=384,
                height=384,
                seed=None,
                num_inference_steps=3,
                guidance_scale=5.0,
                max_vram_gb=7.5,
            )
    finally:
        if original_torch is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = original_torch


def test_to_rgba_image_converts_tensor_output() -> None:
    torch = pytest.importorskip("torch")
    tensor = torch.tensor(
        [
            [
                [-1.0, 1.0],
                [0.0, 0.5],
            ],
            [
                [-1.0, 0.0],
                [1.0, 0.5],
            ],
            [
                [1.0, -1.0],
                [0.0, 0.5],
            ],
            [
                [1.0, 1.0],
                [1.0, 1.0],
            ],
        ],
        dtype=torch.float32,
    )

    image = _to_rgba_image(tensor)

    assert image.mode == "RGBA"
    assert image.size == (2, 2)


def test_sample_latents_offloads_unet_after_sampling() -> None:
    class _FakeGenerator:
        def manual_seed(self, seed: int) -> "_FakeGenerator":
            return self

    class _FakeUnet:
        def __init__(self) -> None:
            self.moves: list[str] = []

        def to(self, device: str) -> "_FakeUnet":
            self.moves.append(device)
            return self

    class _FakeEncoder:
        def to(self, device: str) -> "_FakeEncoder":
            return self

    class _FakePipe:
        def __init__(self) -> None:
            self._execution_device = "cuda"
            self.text_encoder = _FakeEncoder()
            self.text_encoder_2 = _FakeEncoder()
            self.unet = _FakeUnet()
            self.call_kwargs: dict[str, object] = {}

        def encode_prompt(self, **kwargs: object) -> tuple[str, str]:
            return ("prompt", "negative")

        def __call__(self, **kwargs: object) -> tuple[str]:
            self.call_kwargs = kwargs
            return ("latents",)

    fake_torch = SimpleNamespace(
        Generator=lambda device="cpu": _FakeGenerator(),
        cuda=SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None),
    )
    original_torch = sys.modules.get("torch")
    sys.modules["torch"] = fake_torch
    pipe = _FakePipe()
    try:
        latents = _sample_latents(
            pipe=pipe,
            prompts=["a", "b"],
            negative_prompts=["x", "y"],
            width=512,
            height=512,
            generator=None,
            num_inference_steps=10,
            guidance_scale=5.0,
            execution_device="cuda",
            max_vram_gb=None,
        )
    finally:
        if original_torch is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = original_torch

    assert latents == "latents"
    assert pipe.unet.moves == ["cpu"]


def test_configure_scheduler_maps_dpmpp_sde_karras() -> None:
    calls: dict[str, object] = {}

    class _FakeScheduler:
        config = {"foo": "bar"}

    class _FakeSchedulerCls:
        @staticmethod
        def from_config(config: object, **kwargs: object) -> str:
            calls["config"] = config
            calls["kwargs"] = kwargs
            return "configured"

    configured = _configure_scheduler(
        scheduler=_FakeScheduler(),
        sampler_name="DPM++ SDE Karras",
        scheduler_cls=_FakeSchedulerCls,
    )

    assert configured == "configured"
    assert calls["config"] == {"foo": "bar"}
    assert calls["kwargs"] == {
        "algorithm_type": "sde-dpmsolver++",
        "use_karras_sigmas": True,
        "solver_order": 2,
    }


def test_sd15_load_pipeline_uses_custom_rootonchair_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class _FakeTransparentVAE:
        config = SimpleNamespace(force_upcast=True)

        def set_transparent_decoder(self, state_dict: object) -> None:
            calls["decoder_state_dict"] = state_dict

        @classmethod
        def from_pretrained(cls, *args: object, **kwargs: object) -> "_FakeTransparentVAE":
            calls["vae_from_pretrained"] = (args, kwargs)
            return cls()

    class _FakePipe:
        def __init__(self) -> None:
            self.unet = object()

        @classmethod
        def from_pretrained(cls, *args: object, **kwargs: object) -> "_FakePipe":
            calls["pipe_from_pretrained"] = (args, kwargs)
            return cls()

        def load_lora_weights(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("sd15 path should use custom loader")

    def _fake_hf_hub_download(*, repo_id: str, filename: str, cache_dir: str) -> str:
        calls.setdefault("downloads", []).append((repo_id, filename, cache_dir))
        return f"/tmp/{filename}"

    fake_torch = SimpleNamespace(float16="float16", float32="float32")
    class _FakeSchedulerCls:
        @staticmethod
        def from_config(config: object, **kwargs: object) -> object:
            return SimpleNamespace(config=config, kwargs=kwargs)

    fake_diffusers = SimpleNamespace(
        DPMSolverMultistepScheduler=_FakeSchedulerCls,
        StableDiffusionPipeline=_FakePipe,
        StableDiffusionXLPipeline=_FakePipe,
    )
    fake_hf = SimpleNamespace(hf_hub_download=_fake_hf_hub_download)
    fake_safetensors_torch = SimpleNamespace(load_file=lambda path: {"path": path})
    fake_rootonchair_vae = SimpleNamespace(TransparentVAEDecoder=_FakeTransparentVAE)

    def _fake_configure(pipe: object, **kwargs: object) -> object:
        calls["configure"] = kwargs
        return pipe

    def _fake_load_lora_to_unet(unet: object, model_path: str, frames: int = 1) -> None:
        calls["custom_loader"] = (unet, model_path, frames)

    fake_rootonchair_loader = SimpleNamespace(load_lora_to_unet=_fake_load_lora_to_unet)

    original_modules = {
        name: sys.modules.get(name)
        for name in (
            "torch",
            "diffusers",
            "huggingface_hub",
            "safetensors.torch",
            "discoverex.adapters.outbound.models.objects.layerdiffuse.rootonchair_vae",
            "discoverex.adapters.outbound.models.objects.layerdiffuse.rootonchair_sd15.loaders",
        )
    }
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)
    monkeypatch.setitem(sys.modules, "safetensors.torch", fake_safetensors_torch)
    monkeypatch.setitem(
        sys.modules,
        "discoverex.adapters.outbound.models.objects.layerdiffuse.rootonchair_vae",
        fake_rootonchair_vae,
    )
    monkeypatch.setitem(
        sys.modules,
        "discoverex.adapters.outbound.models.objects.layerdiffuse.rootonchair_sd15.loaders",
        fake_rootonchair_loader,
    )

    model = SimpleNamespace(
        model_id="digiplay/Juggernaut_final",
        revision="main",
        weights_cache_dir=".cache/layerdiffuse",
        _layerdiffuse_applied=False,
        offload_mode="sequential",
        enable_attention_slicing=True,
        enable_vae_slicing=True,
        enable_vae_tiling=True,
        enable_xformers_memory_efficient_attention=True,
        enable_fp8_layerwise_casting=False,
        enable_channels_last=True,
        sampler="dpmpp_sde_karras",
    )
    handle = SimpleNamespace(dtype="float16")

    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.objects.layerdiffuse.load.configure_diffusers_pipeline",
        _fake_configure,
    )
    from discoverex.adapters.outbound.models.objects.layerdiffuse import load as layerdiffuse_load

    pipe = layerdiffuse_load.load_pipeline(model=model, handle=handle)

    assert isinstance(pipe, _FakePipe)
    assert calls["decoder_state_dict"] == {"path": "/tmp/layer_sd15_vae_transparent_decoder.safetensors"}
    assert calls["custom_loader"][1] == "/tmp/layer_sd15_transparent_attn.safetensors"
    assert calls["custom_loader"][2] == 1
    assert calls["configure"]["offload_mode"] == "sequential"


def test_load_pipeline_skips_transparent_decoder_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class _FakeAutoencoderKL:
        @classmethod
        def from_pretrained(cls, *args: object, **kwargs: object) -> "_FakeAutoencoderKL":
            calls["vae_from_pretrained"] = (args, kwargs)
            return cls()

    class _FakePipe:
        def __init__(self) -> None:
            self.unet = object()

        @classmethod
        def from_pretrained(cls, *args: object, **kwargs: object) -> "_FakePipe":
            calls["pipe_from_pretrained"] = (args, kwargs)
            return cls()

        def load_lora_weights(self, *args: object, **kwargs: object) -> None:
            calls["load_lora_weights"] = (args, kwargs)

    def _fake_hf_hub_download(*, repo_id: str, filename: str, cache_dir: str) -> str:
        calls.setdefault("downloads", []).append((repo_id, filename, cache_dir))
        return f"/tmp/{filename}"

    fake_torch = SimpleNamespace(float16="float16", float32="float32")

    class _FakeSchedulerCls:
        @staticmethod
        def from_config(config: object, **kwargs: object) -> object:
            return SimpleNamespace(config=config, kwargs=kwargs)

    fake_diffusers = SimpleNamespace(
        AutoencoderKL=_FakeAutoencoderKL,
        DPMSolverMultistepScheduler=_FakeSchedulerCls,
        StableDiffusionPipeline=_FakePipe,
        StableDiffusionXLPipeline=_FakePipe,
    )
    fake_hf = SimpleNamespace(hf_hub_download=_fake_hf_hub_download)
    fake_rootonchair_loader = SimpleNamespace(load_lora_to_unet=lambda *args, **kwargs: None)

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)
    monkeypatch.setitem(
        sys.modules,
        "discoverex.adapters.outbound.models.objects.layerdiffuse.rootonchair_sd15.loaders",
        fake_rootonchair_loader,
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.objects.layerdiffuse.load.configure_diffusers_pipeline",
        lambda pipe, **kwargs: pipe,
    )

    from discoverex.adapters.outbound.models.objects.layerdiffuse import load as layerdiffuse_load

    model = SimpleNamespace(
        model_id="SG161222/RealVisXL_V5.0_Lightning",
        revision="main",
        weights_cache_dir=".cache/layerdiffuse",
        _layerdiffuse_applied=False,
        offload_mode="none",
        enable_attention_slicing=True,
        enable_vae_slicing=True,
        enable_vae_tiling=True,
        enable_xformers_memory_efficient_attention=True,
        enable_fp8_layerwise_casting=False,
        enable_channels_last=True,
        sampler="dpmpp_sde_karras",
        use_transparent_decoder=False,
    )
    handle = SimpleNamespace(dtype="float16")

    pipe = layerdiffuse_load.load_pipeline(model=model, handle=handle)

    assert isinstance(pipe, _FakePipe)
    assert "downloads" not in calls
    assert "load_lora_weights" in calls
