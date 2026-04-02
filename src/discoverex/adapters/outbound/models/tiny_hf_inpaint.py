from __future__ import annotations

from discoverex.models.types import InpaintPrediction, InpaintRequest, ModelHandle


class TinyHFInpaintModel:
    def __init__(
        self,
        model_id: str = "tiny-hf-inpaint",
        device: str = "cpu",
        dtype: str = "float32",
        seed: int | None = 19,
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
            from transformers import BertConfig, BertModel  # type: ignore
        except Exception as exc:
            if self.strict_runtime:
                raise RuntimeError(f"transformers runtime unavailable: {exc}") from exc
            return ModelHandle(
                name="inpaint_model",
                version=model_ref_or_version,
                runtime="tiny_hf_fallback",
                model_id=self.model_id,
                device="cpu",
                dtype=self.dtype,
            )

        if self.seed is not None:
            torch.manual_seed(self.seed)
        cfg = BertConfig(  # type: ignore[no-untyped-call]
            hidden_size=32,
            num_hidden_layers=1,
            num_attention_heads=2,
        )
        model = BertModel(cfg).eval()  # type: ignore[no-untyped-call]
        _ = (
            model(input_ids=torch.ones((1, 8), dtype=torch.long))
            .last_hidden_state.mean()
            .item()
        )
        selected_device = self.device
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            if self.strict_runtime:
                raise RuntimeError(f"requested device '{self.device}' is unavailable")
            selected_device = "cpu"
        return ModelHandle(
            name="inpaint_model",
            version=model_ref_or_version,
            runtime="tiny_hf",
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
        signal = torch.tensor(sum(float(x) for x in bbox), dtype=torch.float32)
        quality = float(torch.sigmoid(signal / 100.0).item())
        return {
            "region_id": request.region_id,
            "quality_score": round(quality, 4),
            "model_id": self.model_id,
            "inpaint_mode": "tiny_hf",
        }
