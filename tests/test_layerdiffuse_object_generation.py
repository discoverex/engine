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
    generate_rgba,
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
            return ([Image.new("RGBA", (384, 384), color=(0, 0, 0, 255))],)

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
    assert pipe.text_encoder.moves == ["cpu"]
    assert pipe.text_encoder_2.moves == ["cpu"]
    assert pipe.pipe_calls[0]["prompt"] is None
    assert pipe.pipe_calls[0]["negative_prompt"] is None
    assert pipe.pipe_calls[0]["num_images_per_prompt"] == 1
    assert pipe.pipe_calls[0]["prompt_embeds"] == "prompt"
    assert ("cpu", "float16") in pipe.vae.moves


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
