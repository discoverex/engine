from __future__ import annotations

from pathlib import Path

from discoverex.adapters.outbound.models.realesrgan_background_upscaler import (
    RealEsrganBackgroundUpscalerModel,
    _extract_state_dict,
)


class _FakeTorch:
    def __init__(self, payload):
        self.payload = payload
        self.saved: list[tuple[object, str]] = []

    def load(self, _path: str, map_location: str = "cpu"):  # type: ignore[no-untyped-def]
        return self.payload

    def save(self, payload: object, path: str) -> None:
        self.saved.append((payload, path))
        Path(path).write_text("normalized", encoding="utf-8")


def test_extract_state_dict_accepts_top_level_tensor_map() -> None:
    checkpoint = {"conv_first.weight": object(), "conv_first.bias": object()}

    assert _extract_state_dict(checkpoint) == checkpoint


def test_extract_state_dict_prefers_named_nested_payloads() -> None:
    checkpoint = {
        "params_ema": {"a": 1},
        "params": {"b": 2},
    }

    assert _extract_state_dict(checkpoint) == {"a": 1}


def test_normalize_checkpoint_wraps_top_level_state_dict(tmp_path: Path) -> None:
    model = RealEsrganBackgroundUpscalerModel(
        model_name="4x-UltraSharp",
        weights_cache_dir=str(tmp_path),
    )
    source = tmp_path / "ultrasharp.pth"
    source.write_text("raw", encoding="utf-8")
    weight = object()
    fake_torch = _FakeTorch({"conv_first.weight": weight})

    normalized = model._normalize_checkpoint_if_needed(
        model_path=source,
        torch_module=fake_torch,
    )

    assert normalized != source
    assert normalized.exists()
    assert fake_torch.saved[0][0] == {
        "params_ema": {"conv_first.weight": weight}
    }


def test_normalize_checkpoint_keeps_standard_payload(tmp_path: Path) -> None:
    model = RealEsrganBackgroundUpscalerModel(
        model_name="RealESRGAN_x2plus",
        weights_cache_dir=str(tmp_path),
    )
    source = tmp_path / "realesrgan.pth"
    source.write_text("raw", encoding="utf-8")
    fake_torch = _FakeTorch({"params": {"conv_first.weight": object()}})

    normalized = model._normalize_checkpoint_if_needed(
        model_path=source,
        torch_module=fake_torch,
    )

    assert normalized == source
    assert fake_torch.saved == []
