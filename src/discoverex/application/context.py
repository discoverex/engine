from __future__ import annotations

from pathlib import Path
from typing import Protocol

from discoverex.application.ports.io import SceneIOPort
from discoverex.application.ports.models import (
    BackgroundGenerationPort,
    FxPort,
    HiddenRegionPort,
    InpaintPort,
    ObjectGenerationPort,
    PerceptionPort,
)
from discoverex.application.ports.reporting import ReportWriterPort
from discoverex.application.ports.storage import (
    ArtifactStorePort,
    MetadataStorePort,
)
from discoverex.application.ports.tracking import TrackerPort
from discoverex.config import (
    ModelVersionsConfig,
    RuntimeConfig,
    ThresholdsConfig,
)


class AppContextLike(Protocol):
    background_generator_model: BackgroundGenerationPort
    object_generator_model: ObjectGenerationPort
    hidden_region_model: HiddenRegionPort
    inpaint_model: InpaintPort
    perception_model: PerceptionPort
    fx_model: FxPort
    artifact_store: ArtifactStorePort
    metadata_store: MetadataStorePort
    tracker: TrackerPort
    scene_io: SceneIOPort
    report_writer: ReportWriterPort
    artifacts_root: Path
    runtime: RuntimeConfig
    thresholds: ThresholdsConfig
    model_versions: ModelVersionsConfig
    execution_snapshot: dict[str, object] | None
    execution_snapshot_path: Path | None
    tracking_run_id: str | None
