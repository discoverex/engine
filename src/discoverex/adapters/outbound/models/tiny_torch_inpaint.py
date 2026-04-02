from __future__ import annotations

from discoverex.models.types import InpaintPrediction, InpaintRequest, ModelHandle


class TinyTorchInpaintModel:
    def __init__(
        self,
        model_id: str = "tiny-torch-inpaint",
        device: str = "cpu",
        dtype: str = "float32",
        seed: int | None = 11,
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
            name="inpaint_model",
            version=model_ref_or_version,
            runtime="tiny_torch",
            model_id=self.model_id,
            device=selected_device,
            dtype=self.dtype,
        )

    def predict(
        self, handle: ModelHandle, request: InpaintRequest
    ) -> InpaintPrediction:
        import torch  # type: ignore

        _ = handle
        bbox = request.bbox or (0.0, 0.0, 1.0, 1.0)
        size_score = torch.tensor(float(bbox[2] * bbox[3]), dtype=torch.float32)
        quality = float(torch.sigmoid(size_score / 50000.0).item())
        return {
            "region_id": request.region_id,
            "quality_score": round(quality, 4),
            "model_id": self.model_id,
            "inpaint_mode": "tiny_torch",
        }
