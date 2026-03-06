from __future__ import annotations

from discoverex.models.types import ModelHandle, PerceptionRequest


class TinyHFPerceptionModel:
    def __init__(
        self,
        model_id: str = "tiny-hf-perception",
        device: str = "cpu",
        dtype: str = "float32",
        seed: int | None = 23,
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
            from transformers import DistilBertConfig, DistilBertModel  # type: ignore
        except Exception as exc:
            if self.strict_runtime:
                raise RuntimeError(f"transformers runtime unavailable: {exc}") from exc
            return ModelHandle(
                name="perception_model",
                version=model_ref_or_version,
                runtime="tiny_hf_fallback",
                model_id=self.model_id,
                device="cpu",
                dtype=self.dtype,
            )

        if self.seed is not None:
            torch.manual_seed(self.seed)
        cfg = DistilBertConfig(
            dim=32,
            hidden_dim=64,
            n_layers=1,
            n_heads=2,
            vocab_size=100,
        )
        model = DistilBertModel(cfg).eval()
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
            name="perception_model",
            version=model_ref_or_version,
            runtime="tiny_hf",
            model_id=self.model_id,
            device=selected_device,
            dtype=self.dtype,
        )

    def predict(
        self, handle: ModelHandle, request: PerceptionRequest
    ) -> dict[str, float]:
        import torch  # type: ignore

        _ = handle
        value = torch.tensor(float(request.region_count), dtype=torch.float32)
        if request.question_context:
            value = value + 1.5
        score = torch.sigmoid((value - 1.0) / 2.0)
        return {"confidence": float(score.item())}
