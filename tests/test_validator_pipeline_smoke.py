from __future__ import annotations

from pathlib import Path

import pytest

from discoverex.adapters.outbound.models.dummy import (
    DummyLogicalExtraction,
    DummyPhysicalExtraction,
    DummyVisualVerification,
)
from discoverex.application.use_cases.validator import ValidatorOrchestrator
from discoverex.domain.verification import VerificationBundle
from discoverex.models.types import ModelHandle


def _make_handle(name: str) -> ModelHandle:
    return ModelHandle(name=name, version="dummy", runtime="dummy")


@pytest.fixture()
def orchestrator() -> ValidatorOrchestrator:
    return ValidatorOrchestrator(
        physical_port=DummyPhysicalExtraction(),
        logical_port=DummyLogicalExtraction(),
        visual_port=DummyVisualVerification(),
        physical_handle=_make_handle("physical"),
        logical_handle=_make_handle("logical"),
        visual_handle=_make_handle("visual"),
    )


class TestValidatorOrchestratorStructure:
    def test_run_returns_verification_bundle(
        self, orchestrator: ValidatorOrchestrator, tmp_path: Path
    ) -> None:
        composite = tmp_path / "composite.png"
        composite.write_bytes(b"fake-image")
        layer = tmp_path / "obj_0.png"
        layer.write_bytes(b"fake-layer")

        bundle = orchestrator.run(composite_image=composite, object_layers=[layer])

        assert isinstance(bundle, VerificationBundle)

    def test_total_score_in_range(
        self, orchestrator: ValidatorOrchestrator, tmp_path: Path
    ) -> None:
        composite = tmp_path / "composite.png"
        composite.write_bytes(b"fake-image")
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            p.write_bytes(b"fake-layer")

        bundle = orchestrator.run(composite_image=composite, object_layers=layers)

        assert 0.0 <= bundle.final.total_score <= 1.0  # 정규화 수식 적용으로 max = 1.0

    def test_pass_field_is_bool(
        self, orchestrator: ValidatorOrchestrator, tmp_path: Path
    ) -> None:
        composite = tmp_path / "composite.png"
        composite.write_bytes(b"fake-image")

        bundle = orchestrator.run(composite_image=composite, object_layers=[])

        assert isinstance(bundle.final.pass_, bool)

    def test_failure_reason_empty_when_pass(
        self, orchestrator: ValidatorOrchestrator, tmp_path: Path
    ) -> None:
        """If the bundle passes, failure_reason must be an empty string."""
        composite = tmp_path / "composite.png"
        composite.write_bytes(b"fake-image")
        layers = [tmp_path / f"obj_{i}.png" for i in range(2)]
        for p in layers:
            p.write_bytes(b"fake-layer")

        bundle = orchestrator.run(composite_image=composite, object_layers=layers)

        if bundle.final.pass_:
            assert bundle.final.failure_reason == ""
        else:
            assert bundle.final.failure_reason != ""

    def test_signals_contain_expected_keys(
        self, orchestrator: ValidatorOrchestrator, tmp_path: Path
    ) -> None:
        composite = tmp_path / "composite.png"
        composite.write_bytes(b"fake-image")

        bundle = orchestrator.run(composite_image=composite, object_layers=[])

        assert "answer_obj_count" in bundle.logical.signals
        assert "sigma_threshold_map" in bundle.perception.signals
        assert "drr_slope_map" in bundle.perception.signals
