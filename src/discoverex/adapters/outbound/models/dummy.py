from __future__ import annotations

from pathlib import Path

from discoverex.models.types import (
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

from .fx_artifact import ensure_output_image


class DummyHiddenRegionModel:
    def load(self, model_ref_or_version: str) -> ModelHandle:
        return ModelHandle(
            name="hidden_region_model",
            version=model_ref_or_version,
            runtime="dummy",
        )

    def predict(
        self,
        handle: ModelHandle,
        request: HiddenRegionRequest | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        _ = handle
        req = request or HiddenRegionRequest(width=width or 0, height=height or 0)
        if width is not None:
            req.width = width
        if height is not None:
            req.height = height
        return [
            (0.10 * req.width, 0.20 * req.height, 0.18 * req.width, 0.22 * req.height),
            (0.45 * req.width, 0.40 * req.height, 0.15 * req.width, 0.20 * req.height),
            (0.72 * req.width, 0.30 * req.height, 0.12 * req.width, 0.16 * req.height),
        ]


class DummyInpaintModel:
    def load(self, model_ref_or_version: str) -> ModelHandle:
        return ModelHandle(
            name="inpaint_model",
            version=model_ref_or_version,
            runtime="dummy",
        )

    def predict(
        self,
        handle: ModelHandle,
        request: InpaintRequest | None = None,
        region_id: str | None = None,
    ) -> InpaintPrediction:
        _ = handle
        req = request or InpaintRequest(region_id=region_id or "")
        if region_id is not None:
            req.region_id = region_id
        return {
            "region_id": req.region_id,
            "quality_score": 0.82,
            "inpaint_mode": "dummy",
        }


class DummyPerceptionModel:
    def load(self, model_ref_or_version: str) -> ModelHandle:
        return ModelHandle(
            name="perception_model",
            version=model_ref_or_version,
            runtime="dummy",
        )

    def predict(
        self,
        handle: ModelHandle,
        request: PerceptionRequest | None = None,
        region_count: int | None = None,
    ) -> dict[str, float]:
        _ = handle
        req = request or PerceptionRequest(region_count=region_count or 0)
        if region_count is not None:
            req.region_count = region_count
        confidence = min(1.0, 0.45 + 0.1 * req.region_count)
        return {"confidence": confidence}


class DummyFxModel:
    def load(self, model_ref_or_version: str) -> ModelHandle:
        return ModelHandle(
            name="fx_model",
            version=model_ref_or_version,
            runtime="dummy",
        )

    def predict(
        self,
        handle: ModelHandle,
        request: FxRequest | None = None,
        mode: str | None = None,
    ) -> FxPrediction:
        _ = handle
        req = request or FxRequest(mode=mode or "default")
        if mode is not None:
            req.mode = mode
        prediction: FxPrediction = {"fx": req.mode or "none"}
        output_path = req.params.get("output_path")
        if isinstance(output_path, str) and output_path:
            ensure_output_image(output_path)
            prediction["output_path"] = output_path
        return prediction


# ---------------------------------------------------------------------------
# Validator pipeline dummy adapters (load/extract|verify/unload pattern)
# ---------------------------------------------------------------------------


class DummyPhysicalExtraction:
    """Dummy Phase 1: returns fixed physical metadata for two objects."""

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def extract(
        self,
        composite_image: Path,
        object_layers: list[Path],  # noqa: ARG002
    ) -> PhysicalMetadata:
        obj_ids = [f"obj_{i}" for i in range(len(object_layers))] or ["obj_0", "obj_1"]
        return PhysicalMetadata(
            regions=[{"obj_id": oid, "bbox": [0.1, 0.1, 0.2, 0.2]} for oid in obj_ids],
            occlusion_map={oid: 0.45 for oid in obj_ids},
            z_index_map={oid: i for i, oid in enumerate(obj_ids)},
            z_depth_hop_map={oid: 2 for oid in obj_ids},
            cluster_density_map={oid: 3 for oid in obj_ids},
            euclidean_distance_map={oid: [50.0, 80.0] for oid in obj_ids},
        )

    def unload(self) -> None:
        pass


class DummyLogicalExtraction:
    """Dummy Phase 2: returns fixed scene graph metrics."""

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def extract(
        self,
        composite_image: Path,
        physical: PhysicalMetadata,  # noqa: ARG002
    ) -> LogicalStructure:
        obj_ids = list(physical.occlusion_map.keys()) or ["obj_0", "obj_1"]
        return LogicalStructure(
            relations=[
                {"subject": obj_ids[0], "predicate": "near", "object": obj_ids[-1]}
            ],
            degree_map={oid: 3 for oid in obj_ids},
            hop_map={oid: 2 for oid in obj_ids},
            diameter=4.0,
        )

    def unload(self) -> None:
        pass


class DummyVisualVerification:
    """Dummy Phase 3: returns fixed sigma threshold and DRR slope values."""

    def load(self, handle: ModelHandle) -> None:  # noqa: ARG002
        pass

    def verify(
        self,
        composite_image: Path,
        sigma_levels: list[float],  # noqa: ARG002
    ) -> VisualVerification:
        # Use deterministic obj IDs — orchestrator unifies by intersection of maps
        obj_ids = ["obj_0", "obj_1"]
        return VisualVerification(
            sigma_threshold_map={oid: 4.0 for oid in obj_ids},
            drr_slope_map={oid: 0.15 for oid in obj_ids},
        )

    def unload(self) -> None:
        pass
