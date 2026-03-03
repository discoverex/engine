from __future__ import annotations

from typing import Protocol

from discoverex.models.types import (
    FxPrediction,
    FxRequest,
    HiddenRegionRequest,
    InpaintPrediction,
    InpaintRequest,
    ModelHandle,
    PerceptionRequest,
)


class HiddenRegionPort(Protocol):
    def load(self, model_ref_or_version: str) -> ModelHandle: ...

    def predict(
        self, handle: ModelHandle, request: HiddenRegionRequest
    ) -> list[tuple[float, float, float, float]]: ...


class InpaintPort(Protocol):
    def load(self, model_ref_or_version: str) -> ModelHandle: ...

    def predict(
        self, handle: ModelHandle, request: InpaintRequest
    ) -> InpaintPrediction: ...


class PerceptionPort(Protocol):
    def load(self, model_ref_or_version: str) -> ModelHandle: ...

    def predict(
        self, handle: ModelHandle, request: PerceptionRequest
    ) -> dict[str, float]: ...


class FxPort(Protocol):
    def load(self, model_ref_or_version: str) -> ModelHandle: ...

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction: ...
