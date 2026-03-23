from __future__ import annotations

from pathlib import Path

from discoverex.adapters.outbound.models.realesrgan_background_upscaler import (
    RealEsrganBackgroundUpscalerModel,
    _extract_state_dict,
    _normalize_state_dict_keys,
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


def test_normalize_state_dict_keys_converts_legacy_esrgan_layout() -> None:
    checkpoint = {
        "model.0.weight": "w0",
        "model.0.bias": "b0",
        "model.1.sub.0.RDB1.conv1.0.weight": "rw",
        "model.1.sub.0.RDB1.conv1.0.bias": "rb",
        "model.1.sub.23.weight": "tw",
        "model.1.sub.23.bias": "tb",
        "model.3.weight": "u1w",
        "model.3.bias": "u1b",
        "model.6.weight": "u2w",
        "model.6.bias": "u2b",
        "model.8.weight": "hrw",
        "model.8.bias": "hrb",
        "model.10.weight": "clw",
        "model.10.bias": "clb",
    }

    normalized = _normalize_state_dict_keys(checkpoint)

    assert normalized["conv_first.weight"] == "w0"
    assert normalized["body.0.rdb1.conv1.weight"] == "rw"
    assert normalized["body.0.rdb1.conv1.bias"] == "rb"
    assert normalized["conv_body.weight"] == "tw"
    assert normalized["conv_up1.weight"] == "u1w"
    assert normalized["conv_up2.bias"] == "u2b"
    assert normalized["conv_hr.weight"] == "hrw"
    assert normalized["conv_last.bias"] == "clb"


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
