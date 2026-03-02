from __future__ import annotations

from discoverex.models.types import HiddenRegionRequest, ModelHandle


class TinyTorchHiddenRegionModel:
    def __init__(
        self,
        model_id: str = "tiny-torch-hidden",
        device: str = "cpu",
        dtype: str = "float32",
        seed: int | None = 7,
        strict_runtime: bool = True,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.seed = seed
        self.strict_runtime = strict_runtime

    def load(self, model_ref_or_version: str) -> ModelHandle:
        import torch  # type: ignore

        if self.seed is not None:
            torch.manual_seed(self.seed)
        selected_device = self.device
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            if self.strict_runtime:
                raise RuntimeError(f"requested device '{self.device}' is unavailable")
            selected_device = "cpu"
        return ModelHandle(
            name="hidden_region_model",
            version=model_ref_or_version,
            runtime="tiny_torch",
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
                [0.12, 0.20, 0.18, 0.20],
                [0.45, 0.42, 0.16, 0.18],
                [0.70, 0.30, 0.12, 0.14],
            ],
            dtype=torch.float32,
        )
        scale = torch.tensor([width, height, width, height], dtype=torch.float32)
        boxes = base * scale
        return [tuple(float(v) for v in row.tolist()) for row in boxes]
