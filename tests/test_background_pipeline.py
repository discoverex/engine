from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from discoverex.application.use_cases.gen_verify.background_pipeline import (
    _read_background_image_size,
    apply_background_hires_fix_if_needed,
)
from discoverex.domain.scene import Background


def test_read_background_image_size_reports_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "background.png"
    Image.new("RGB", (64, 48), color=(120, 140, 160)).save(source)

    result = _read_background_image_size(image_path=source)

    assert result["path"] == source
    assert result["width"] == 64
    assert result["height"] == 48


def test_apply_background_hires_fix_updates_background_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "background.png"
    output = tmp_path / "assets" / "background" / "generated-background.hiresfix.png"
    Image.new("RGB", (64, 48), color=(120, 140, 160)).save(source)

    class _FakeBackgroundModel:
        def predict(self, _handle, request):  # type: ignore[no-untyped-def]
            image = Image.open(request.image_ref).convert("RGB")
            resized = image.resize((256, 192), Image.Resampling.LANCZOS)
            Path(request.params["output_path"]).parent.mkdir(parents=True, exist_ok=True)
            resized.save(request.params["output_path"])
            return {"output_path": request.params["output_path"]}

    background = Background(asset_ref=str(source), width=64, height=48)
    context = SimpleNamespace(
        runtime=SimpleNamespace(
            width=64,
            height=48,
            background_upscale_factor=4,
            model_runtime=SimpleNamespace(seed=None),
        ),
        background_upscaler_model=_FakeBackgroundModel(),
    )

    updated = apply_background_hires_fix_if_needed(
        background=background,
        context=context,
        scene_dir=tmp_path,
        upscaler_handle=object(),
        prompt="stormy harbor",
        negative_prompt="blurry",
    )

    assert updated.asset_ref == str(output)
    assert updated.width == 256
    assert updated.height == 192
    assert updated.metadata["base_background_ref"] == str(source)
    assert updated.metadata["background_upscale_factor"] == 4
    assert context.runtime.width == 256
    assert context.runtime.height == 192
