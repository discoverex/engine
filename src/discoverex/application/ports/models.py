from __future__ import annotations

from pathlib import Path
from typing import Protocol

from discoverex.domain.verification import VerificationBundle
from discoverex.models.types import (
    ColorEdgeMetadata,
    FxPrediction,
    FxRequest,
    HiddenRegionRequest,
    InpaintPrediction,
    InpaintRequest,
    LogicalStructure,
    ModelHandle,
    PerceptionRequest,
    PhysicalMetadata,
    VisualVerification,
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


class BackgroundGenerationPort(Protocol):
    def load(self, model_ref_or_version: str) -> ModelHandle: ...

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction: ...


class ObjectGenerationPort(Protocol):
    def load(self, model_ref_or_version: str) -> ModelHandle: ...

    def predict(self, handle: ModelHandle, request: FxRequest) -> FxPrediction: ...


# ---------------------------------------------------------------------------
# Validator pipeline ports — load/extract(verify)/unload pattern
# Each port is responsible for its own VRAM lifecycle.
# ---------------------------------------------------------------------------


class PhysicalExtractionPort(Protocol):
    """Phase 1: MobileSAM-based physical metadata extraction."""

    def load(self, handle: ModelHandle) -> None: ...

    def extract(
        self, composite_image: Path, object_layers: list[Path]
    ) -> PhysicalMetadata: ...

    def unload(self) -> None: ...


class ColorEdgeExtractionPort(Protocol):
    """Phase 2: Classical CV color contrast + edge strength extraction (CPU-only, no model)."""

    def load(self, handle: ModelHandle) -> None: ...

    def extract(
        self, composite_image: Path, object_layers: list[Path]
    ) -> ColorEdgeMetadata: ...

    def unload(self) -> None: ...


class LogicalExtractionPort(Protocol):
    """Phase 3: Moondream2-based scene graph + logical relation extraction."""

    def load(self, handle: ModelHandle) -> None: ...

    def extract(
        self, composite_image: Path, physical: PhysicalMetadata
    ) -> LogicalStructure: ...

    def unload(self) -> None: ...


class VisualVerificationPort(Protocol):
    """Phase 4: YOLO+CLIP parallel visual difficulty verification."""

    def load(self, handle: ModelHandle) -> None: ...

    def verify(
        self,
        composite_image: Path,
        sigma_levels: list[float],
        color_edge: ColorEdgeMetadata | None = None,
        physical: PhysicalMetadata | None = None,
    ) -> VisualVerification: ...

    def unload(self) -> None: ...


class BundleStorePort(Protocol):
    """MVP 데이터 수집: VerificationBundle 을 영속화하는 아웃바운드 포트."""

    def save(
        self,
        bundle: VerificationBundle,
        composite_image: Path,
        object_layers: list[Path],
    ) -> None: ...
