from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

import pytest

from discoverex.adapters.outbound.models.realvisxl_lightning_background_generation import (
    RealVisXLLightningBackgroundGenerationModel,
)
from discoverex.adapters.outbound.models.runtime import RuntimeResolution
from discoverex.models.types import FxRequest


class _FakeImage:
    def __init__(self, width: int = 64, height: int = 64) -> None:
        self.width = width
        self.height = height

    def save(self, path: Path) -> None:
        path.write_bytes(b"fake-image")

    def resize(self, size: tuple[int, int], _resample: Any = None) -> "_FakeImage":
        return _FakeImage(width=size[0], height=size[1])

    def convert(self, _mode: str) -> "_FakeImage":
        return self

    def __enter__(self) -> "_FakeImage":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        return False


class _FakeUpscaler:
    def __init__(self) -> None:
        self.calls: list[FxRequest] = []

    def predict(self, _handle: Any, request: FxRequest) -> dict[str, str]:
        self.calls.append(request)
        output_path = Path(str(request.params["output_path"]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"upscaled")
        return {"fx": "background_canvas_upscale", "output_path": str(output_path)}

    def unload(self) -> None:
        return None


def _runtime() -> RuntimeResolution:
    return RuntimeResolution(
        available=True,
        torch=None,
        transformers=type(
            "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
        )(),
        reason="",
    )


def test_realvisxl_lightning_background_generation_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    model = RealVisXLLightningBackgroundGenerationModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.resolve_runtime",
        _runtime,
    )
    handle = model.load("bg-v1")

    def _fake_generate_image(**kwargs: Any) -> _FakeImage:
        captured.update(kwargs)
        return _FakeImage(width=512, height=384)

    monkeypatch.setattr(model, "_generate_image", _fake_generate_image)

    output_path = tmp_path / "background.png"
    pred = model.predict(
        handle,
        FxRequest(
            mode="background",
            params={
                "output_path": str(output_path),
                "prompt": "stormy harbor",
                "width": 512,
                "height": 384,
            },
        ),
    )

    assert pred["output_path"] == str(output_path)
    assert output_path.exists()
    assert captured["prompt"] == "stormy harbor"
    assert captured["num_inference_steps"] == 5
    assert captured["guidance_scale"] == 2.0


def test_realvisxl_lightning_canvas_upscale_uses_internal_upscaler(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = RealVisXLLightningBackgroundGenerationModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.resolve_runtime",
        _runtime,
    )
    handle = model.load("bg-v1")
    fake_upscaler = _FakeUpscaler()
    monkeypatch.setattr(model, "_load_canvas_upscaler", lambda _handle: fake_upscaler)
    model._canvas_upscaler_handle = handle

    source_path = tmp_path / "source.png"
    source_path.write_bytes(b"seed")
    output_path = tmp_path / "background.canvas.png"

    pred = model.predict(
        handle,
        FxRequest(
            mode="canvas_upscale",
            image_ref=str(source_path),
            params={
                "output_path": str(output_path),
                "width": 1024,
                "height": 768,
            },
        ),
    )

    assert pred["fx"] == "background_canvas_upscale"
    assert output_path.exists()
    assert fake_upscaler.calls[0].params["width"] == 1024
    assert fake_upscaler.calls[0].params["height"] == 768


def test_realvisxl_lightning_hires_fix_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    model = RealVisXLLightningBackgroundGenerationModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.resolve_runtime",
        _runtime,
    )
    handle = model.load("bg-v1")
    source_path = tmp_path / "source.png"
    source_path.write_bytes(b"seed")
    monkeypatch.setattr(
        "PIL.Image.open",
        lambda *_args, **_kwargs: _FakeImage(width=1024, height=1024),
    )

    def _fake_reconstruct_image(**kwargs: Any) -> _FakeImage:
        captured.update(kwargs)
        return kwargs["image"]

    monkeypatch.setattr(model, "_reconstruct_image", _fake_reconstruct_image)

    output_path = tmp_path / "background.hiresfix.png"
    pred = model.predict(
        handle,
        FxRequest(
            mode="detail_reconstruct",
            image_ref=str(source_path),
            params={
                "output_path": str(output_path),
                "width": 2048,
                "height": 2048,
                "prompt": "stormy harbor",
            },
        ),
    )

    assert pred["fx"] == "background_detail_reconstruct"
    assert pred["output_path"] == str(output_path)
    assert output_path.exists()
    assert captured["num_inference_steps"] == 3
    assert captured["guidance_scale"] == 2.0
    assert captured["strength"] == 0.5


class _FakeScheduler:
    config = {"name": "scheduler"}


class _FakePipeline:
    def __init__(self) -> None:
        self.scheduler = _FakeScheduler()


def test_realvisxl_base_loader_uses_fp16_variant_and_cache_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    configure_calls: dict[str, Any] = {}
    model = RealVisXLLightningBackgroundGenerationModel(
        strict_runtime=False,
        offload_mode="sequential",
        model_cache_dir="/cache/models",
        hf_home="/cache/models/hf",
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.resolve_runtime",
        _runtime,
    )
    handle = model.load("bg-v1")

    class _FakeTorch:
        float16 = "float16"
        float32 = "float32"

    class _FakeDpm:
        @classmethod
        def from_config(cls, config: Any, **kwargs: Any) -> _FakeScheduler:
            calls["scheduler_kwargs"] = kwargs
            return _FakeScheduler()

    class _FakeText2Image:
        @staticmethod
        def from_pretrained(*args: Any, **kwargs: Any) -> _FakePipeline:
            calls["args"] = args
            calls["kwargs"] = kwargs
            return _FakePipeline()

    fake_diffusers = type(
        "_FakeDiffusers",
        (),
        {
            "AutoPipelineForText2Image": _FakeText2Image,
            "DPMSolverMultistepScheduler": _FakeDpm,
        },
    )()

    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    def _fake_configure(pipe: Any, **kwargs: Any) -> Any:
        configure_calls["kwargs"] = kwargs
        return pipe

    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.configure_diffusers_pipeline",
        _fake_configure,
    )

    model._load_base_pipe(handle)

    assert calls["args"] == (model.model_id,)
    assert calls["kwargs"]["variant"] == "fp16"
    assert calls["kwargs"]["use_safetensors"] is True
    assert calls["kwargs"]["add_watermarker"] is False
    assert calls["kwargs"]["cache_dir"] == "/cache/models/hf"
    assert configure_calls["kwargs"]["offload_mode"] == "model"


def test_realvisxl_detail_loader_uses_fp16_variant_and_cache_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    configure_calls: dict[str, Any] = {}
    model = RealVisXLLightningBackgroundGenerationModel(
        strict_runtime=False,
        offload_mode="sequential",
        model_cache_dir="/cache/models",
        hf_home="/cache/models/hf",
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.resolve_runtime",
        _runtime,
    )
    handle = model.load("bg-v1")

    class _FakeTorch:
        float16 = "float16"
        float32 = "float32"

    class _FakeDpm:
        @classmethod
        def from_config(cls, config: Any, **kwargs: Any) -> _FakeScheduler:
            calls["scheduler_kwargs"] = kwargs
            return _FakeScheduler()

    class _FakeImage2Image:
        @staticmethod
        def from_pretrained(*args: Any, **kwargs: Any) -> _FakePipeline:
            calls["args"] = args
            calls["kwargs"] = kwargs
            return _FakePipeline()

    fake_diffusers = type(
        "_FakeDiffusers",
        (),
        {
            "AutoPipelineForImage2Image": _FakeImage2Image,
            "DPMSolverMultistepScheduler": _FakeDpm,
        },
    )()

    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    def _fake_configure(pipe: Any, **kwargs: Any) -> Any:
        configure_calls["kwargs"] = kwargs
        return pipe

    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.configure_diffusers_pipeline",
        _fake_configure,
    )

    model._load_detail_pipe(handle)

    assert calls["args"] == (model.model_id,)
    assert calls["kwargs"]["variant"] == "fp16"
    assert calls["kwargs"]["use_safetensors"] is True
    assert calls["kwargs"]["add_watermarker"] is False
    assert calls["kwargs"]["cache_dir"] == "/cache/models/hf"
    assert configure_calls["kwargs"]["offload_mode"] == "model"


def test_realvisxl_diffusers_cache_dir_falls_back_to_model_cache_dir() -> None:
    model = RealVisXLLightningBackgroundGenerationModel(
        strict_runtime=False,
        model_cache_dir="/cache/models",
        hf_home="",
    )

    assert model._diffusers_cache_dir() == "/cache/models/hf"


def test_realvisxl_base_loader_tries_local_files_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    model = RealVisXLLightningBackgroundGenerationModel(
        strict_runtime=False,
        model_cache_dir="/cache/models",
        hf_home="/cache/models/hf",
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.resolve_runtime",
        _runtime,
    )
    monkeypatch.setattr(
        model,
        "_missing_snapshot_files",
        lambda _cache_dir: [],
    )
    monkeypatch.setattr(
        model,
        "_snapshot_dir",
        lambda _cache_dir: "/cache/models/hf/hub/models--SG161222--RealVisXL_V5.0_Lightning/snapshots/main",
    )
    handle = model.load("bg-v1")

    class _FakeTorch:
        float16 = "float16"
        float32 = "float32"

    class _FakeDpm:
        @classmethod
        def from_config(cls, config: Any, **kwargs: Any) -> _FakeScheduler:
            return _FakeScheduler()

    class _FakeText2Image:
        @staticmethod
        def from_pretrained(*args: Any, **kwargs: Any) -> _FakePipeline:
            calls.append({"args": args, "kwargs": kwargs})
            return _FakePipeline()

    fake_diffusers = type(
        "_FakeDiffusers",
        (),
        {
            "AutoPipelineForText2Image": _FakeText2Image,
            "DPMSolverMultistepScheduler": _FakeDpm,
        },
    )()
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.configure_diffusers_pipeline",
        lambda pipe, **kwargs: pipe,
    )

    model._load_base_pipe(handle)

    assert len(calls) == 1
    assert calls[0]["kwargs"]["local_files_only"] is True


def test_realvisxl_base_loader_falls_back_to_remote_on_local_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    model = RealVisXLLightningBackgroundGenerationModel(
        strict_runtime=False,
        model_cache_dir="/cache/models",
        hf_home="/cache/models/hf",
    )
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.resolve_runtime",
        _runtime,
    )
    monkeypatch.setattr(
        model,
        "_missing_snapshot_files",
        lambda _cache_dir: [],
    )
    monkeypatch.setattr(
        model,
        "_snapshot_dir",
        lambda _cache_dir: "/cache/models/hf/hub/models--SG161222--RealVisXL_V5.0_Lightning/snapshots/main",
    )
    handle = model.load("bg-v1")

    class _FakeTorch:
        float16 = "float16"
        float32 = "float32"

    class _FakeDpm:
        @classmethod
        def from_config(cls, config: Any, **kwargs: Any) -> _FakeScheduler:
            return _FakeScheduler()

    class _FakeText2Image:
        @staticmethod
        def from_pretrained(*args: Any, **kwargs: Any) -> _FakePipeline:
            calls.append({"args": args, "kwargs": kwargs})
            if kwargs.get("local_files_only") is True:
                raise OSError("missing local snapshot")
            return _FakePipeline()

    fake_diffusers = type(
        "_FakeDiffusers",
        (),
        {
            "AutoPipelineForText2Image": _FakeText2Image,
            "DPMSolverMultistepScheduler": _FakeDpm,
        },
    )()
    monkeypatch.setitem(sys.modules, "torch", _FakeTorch())
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.realvisxl_lightning_background_generation.configure_diffusers_pipeline",
        lambda pipe, **kwargs: pipe,
    )

    model._load_base_pipe(handle)

    assert len(calls) == 2
    assert calls[0]["kwargs"]["local_files_only"] is True
    assert "local_files_only" not in calls[1]["kwargs"]
