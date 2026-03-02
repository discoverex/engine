from __future__ import annotations

from discoverex.models.types import ModelHandle, PerceptionRequest


class TinyTorchPerceptionModel:
    def __init__(
        self,
        model_id: str = "tiny-torch-perception",
        device: str = "cpu",
        dtype: str = "float32",
        seed: int | None = 13,
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
            name="perception_model",
            version=model_ref_or_version,
            runtime="tiny_torch",
            model_id=self.model_id,
            device=selected_device,
            dtype=self.dtype,
        )

    def predict(self, handle: ModelHandle, request: PerceptionRequest) -> dict[str, float]:
        import torch  # type: ignore

        _ = handle
        x = torch.tensor([float(request.region_count), float(bool(request.question_context))])
        score = torch.sigmoid(0.2 * x[0] + 0.6 * x[1] - 0.3)
        return {"confidence": float(score.item())}
