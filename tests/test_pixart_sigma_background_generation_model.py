from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import pytest

from discoverex.adapters.outbound.models.pixart_sigma_background_generation import (
    PixArtSigmaBackgroundGenerationModel,
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


def test_pixart_background_generation_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    model = PixArtSigmaBackgroundGenerationModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.pixart_sigma_background_generation.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("bg-v1")

    def _fake_generate_base_image(**kwargs: Any) -> _FakeImage:
        captured.update(kwargs)
        return _FakeImage(width=1024, height=1024)

    monkeypatch.setattr(model, "_generate_base_image", _fake_generate_base_image)

    output_path = tmp_path / "background.png"
    pred = model.predict(
        handle,
        FxRequest(
            mode="background",
            params={
                "output_path": str(output_path),
                "prompt": "misty harbor",
                "width": 1024,
                "height": 1024,
            },
        ),
    )

    assert pred["output_path"] == str(output_path)
    assert output_path.exists()
    assert captured["prompt"] == "misty harbor"
    assert captured["width"] == 1024


def test_pixart_hires_fix_writes_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = PixArtSigmaBackgroundGenerationModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.pixart_sigma_background_generation.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("bg-v1")
    source_path = tmp_path / "source.png"
    source_path.write_bytes(b"seed")

    monkeypatch.setattr(
        "PIL.Image.open",
        lambda *_args, **_kwargs: _FakeImage(width=1024, height=1024),
    )
    monkeypatch.setattr(
        model,
        "_reconstruct_details",
        lambda **kwargs: kwargs["image"],
    )

    output_path = tmp_path / "background.hiresfix.png"
    pred = model.predict(
        handle,
        FxRequest(
            mode="hires_fix",
            params={
                "image_ref": str(source_path),
                "output_path": str(output_path),
                "width": 2048,
                "height": 2048,
                "prompt": "misty harbor",
            },
        ),
    )

    assert pred["fx"] == "background_hires_fix"
    assert pred["output_path"] == str(output_path)
    assert output_path.exists()


def test_pixart_canvas_upscale_resizes_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model = PixArtSigmaBackgroundGenerationModel(strict_runtime=False)
    monkeypatch.setattr(
        "discoverex.adapters.outbound.models.pixart_sigma_background_generation.resolve_runtime",
        lambda: RuntimeResolution(
            available=True,
            torch=None,
            transformers=type(
                "_TfCompat", (), {"__version__": "4.46.0", "MT5Tokenizer": object()}
            )(),
            reason="",
        ),
    )
    handle = model.load("bg-v1")
    source_path = tmp_path / "source.png"
    source_path.write_bytes(b"seed")
    monkeypatch.setattr(
        "PIL.Image.open",
        lambda *_args, **_kwargs: _FakeImage(width=512, height=512),
    )

    pred = model.predict(
        handle,
        FxRequest(
            mode="canvas_upscale",
            params={
                "image_ref": str(source_path),
                "output_path": str(tmp_path / "upscaled.png"),
                "width": 1024,
                "height": 1024,
            },
        ),
    )

    assert pred["fx"] == "background_canvas_upscale"
    assert Path(pred["output_path"]).exists()
