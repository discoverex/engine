from __future__ import annotations

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle


class TinyTorchFxModel:
    def __init__(
        self,
        model_id: str = "tiny-torch-fx",
        device: str = "cpu",
        dtype: str = "float32",
        strict_runtime: bool = True,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.strict_runtime = strict_runtime

    def load(self, model_ref_or_version: str) -> ModelHandle:
        return ModelHandle(
            name="fx_model",
            version=model_ref_or_version,
            runtime="tiny_torch",
            model_id=self.model_id,
            device=self.device,
            dtype=self.dtype,
        )

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction:
        _ = handle
        prediction: FxPrediction = {"fx": request.mode or "default"}
        output_path = request.params.get("output_path")
        if isinstance(output_path, str) and output_path:
            prediction["output_path"] = output_path
        return prediction
