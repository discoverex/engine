from __future__ import annotations

from discoverex.models.types import HiddenRegionRequest, ModelHandle


class TinyHFHiddenRegionModel:
    def __init__(
        self,
        model_id: str = "tiny-hf-hidden",
        device: str = "cpu",
        dtype: str = "float32",
        seed: int | None = 17,
        strict_runtime: bool = True,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.seed = seed
        self.strict_runtime = strict_runtime

    def load(self, model_ref_or_version: str) -> ModelHandle:
        import torch  # type: ignore

        try:
            from transformers import ViTConfig, ViTModel  # type: ignore
        except Exception as exc:
            if self.strict_runtime:
                raise RuntimeError(f"transformers runtime unavailable: {exc}") from exc
            return ModelHandle(
                name="hidden_region_model",
                version=model_ref_or_version,
                runtime="tiny_hf_fallback",
                model_id=self.model_id,
                device="cpu",
                dtype=self.dtype,
            )

        if self.seed is not None:
            torch.manual_seed(self.seed)
        cfg = ViTConfig(
            image_size=32,
            patch_size=16,
            hidden_size=32,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=64,
        )
        model = ViTModel(cfg).eval()
        _ = model(torch.randn(1, 3, 32, 32)).last_hidden_state.mean().item()
        selected_device = self.device
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            if self.strict_runtime:
                raise RuntimeError(f"requested device '{self.device}' is unavailable")
            selected_device = "cpu"
        return ModelHandle(
            name="hidden_region_model",
            version=model_ref_or_version,
            runtime="tiny_hf",
            model_id=self.model_id,
            device=selected_device,
            dtype=self.dtype,
        )

    def predict(
        self, handle: ModelHandle, request: HiddenRegionRequest
    ) -> list[tuple[float, float, float, float]]:
        import torch  # type: ignore

        _ = handle
        width = max(1, int(request.width))
        height = max(1, int(request.height))
        base = torch.tensor(
            [
                [0.10, 0.16, 0.18, 0.20],
                [0.42, 0.44, 0.17, 0.19],
                [0.74, 0.28, 0.11, 0.15],
            ],
            dtype=torch.float32,
        )
        scale = torch.tensor([width, height, width, height], dtype=torch.float32)
        boxes = base * scale
        result: list[tuple[float, float, float, float]] = []
        for row in boxes.tolist():
            x, y, w, h = row
            result.append((float(x), float(y), float(w), float(h)))
        return result
