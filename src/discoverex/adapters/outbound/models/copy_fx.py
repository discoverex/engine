from __future__ import annotations

import shutil
from pathlib import Path

from discoverex.models.types import FxPrediction, FxRequest, ModelHandle


class CopyImageFxModel:
    def load(self, model_ref_or_version: str) -> ModelHandle:
        return ModelHandle(
            name="fx_model",
            version=model_ref_or_version,
            runtime="copy_image",
        )

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction:
        _ = handle
        output_path = request.params.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            raise ValueError("FxRequest.params.output_path is required")
        source = request.image_ref
        if source is None:
            raise ValueError("FxRequest.image_ref is required for copy fx")
        source_path = Path(str(source))
        if not source_path.exists():
            raise ValueError(f"copy fx source image does not exist: {source_path}")
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        return {"fx": request.mode or "copy_image", "output_path": str(target)}
