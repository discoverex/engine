from __future__ import annotations

from pathlib import Path

from discoverex.application.ports.models import (
    BundleStorePort,
    LogicalExtractionPort,
    PhysicalExtractionPort,
    VisualVerificationPort,
)
from discoverex.domain.services.verification import ScoringWeights
from discoverex.domain.verification import VerificationBundle
from discoverex.models.types import (
    LogicalStructure,
    ModelHandle,
    PhysicalMetadata,
    ValidatorInput,
    VisualVerification,
)

from .scoring import build_verification_bundle

_DEFAULT_SIGMA_LEVELS: list[float] = [1.0, 2.0, 4.0, 8.0, 16.0]


class ValidatorOrchestrator:
    def __init__(
        self,
        physical_port: PhysicalExtractionPort,
        logical_port: LogicalExtractionPort,
        visual_port: VisualVerificationPort,
        physical_handle: ModelHandle,
        logical_handle: ModelHandle,
        visual_handle: ModelHandle,
        pass_threshold: float = 0.35,
        scoring_weights: ScoringWeights | None = None,
        sigma_levels: list[float] | None = None,
        bundle_store: BundleStorePort | None = None,
    ) -> None:
        self._physical_port = physical_port
        self._logical_port = logical_port
        self._visual_port = visual_port
        self._physical_handle = physical_handle
        self._logical_handle = logical_handle
        self._visual_handle = visual_handle
        self._pass_threshold = pass_threshold
        self._weights = scoring_weights or ScoringWeights()
        self._sigma_levels = sigma_levels or _DEFAULT_SIGMA_LEVELS
        self._bundle_store = bundle_store

    def run(
        self, composite_image: Path, object_layers: list[Path]
    ) -> VerificationBundle:
        physical = self._run_phase1(composite_image, object_layers)
        logical = self._run_phase2(composite_image, physical)
        visual = self._run_phase3(composite_image)
        bundle = self._run_phase4(
            ValidatorInput(physical=physical, logical=logical, visual=visual)
        )
        if self._bundle_store is not None:
            self._bundle_store.save(bundle, composite_image, object_layers)
        return bundle

    def _run_phase1(
        self,
        composite_image: Path,
        object_layers: list[Path],
    ) -> PhysicalMetadata:
        self._physical_port.load(self._physical_handle)
        try:
            return self._physical_port.extract(composite_image, object_layers)
        finally:
            self._physical_port.unload()

    def _run_phase2(
        self,
        composite_image: Path,
        physical: PhysicalMetadata,
    ) -> LogicalStructure:
        self._logical_port.load(self._logical_handle)
        try:
            return self._logical_port.extract(composite_image, physical)
        finally:
            self._logical_port.unload()

    def _run_phase3(self, composite_image: Path) -> VisualVerification:
        self._visual_port.load(self._visual_handle)
        try:
            return self._visual_port.verify(composite_image, self._sigma_levels)
        finally:
            self._visual_port.unload()

    def _run_phase4(self, data: ValidatorInput) -> VerificationBundle:
        return build_verification_bundle(
            data,
            pass_threshold=self._pass_threshold,
            weights=self._weights,
        )


def run_validator(
    composite_image: Path,
    object_layers: list[Path],
    orchestrator: ValidatorOrchestrator,
) -> VerificationBundle:
    return orchestrator.run(composite_image, object_layers)
