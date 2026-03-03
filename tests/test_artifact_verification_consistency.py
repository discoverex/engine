from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from discoverex.adapters.outbound.io.reports import JsonReportWriterAdapter
from discoverex.adapters.outbound.storage.artifact import LocalArtifactStoreAdapter
from discoverex.domain.goal import AnswerForm, Goal, GoalType
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.scene import (
    Answer,
    Background,
    Composite,
    Difficulty,
    LayerItem,
    LayerStack,
    LayerType,
    Scene,
    SceneMeta,
    SceneStatus,
)
from discoverex.domain.verification import (
    FinalVerification,
    VerificationBundle,
    VerificationResult,
)


def _build_scene() -> Scene:
    now = datetime.now(timezone.utc)
    return Scene(
        meta=SceneMeta(
            scene_id="scene-consistency",
            version_id="v-consistency",
            status=SceneStatus.APPROVED,
            pipeline_run_id="run-consistency",
            model_versions={},
            config_version="config-v1",
            created_at=now,
            updated_at=now,
        ),
        background=Background(asset_ref="bg://consistency", width=64, height=64),
        regions=[
            Region(
                region_id="r1",
                geometry=Geometry(type="bbox", bbox=BBox(x=1, y=2, w=3, h=4)),
                role=RegionRole.ANSWER,
                source=RegionSource.MANUAL,
                attributes={},
                version=1,
            )
        ],
        composite=Composite(final_image_ref="artifacts/example/composite.png"),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id="layer-base",
                    type=LayerType.BASE,
                    image_ref="bg://consistency",
                    z_index=0,
                    order=0,
                ),
                LayerItem(
                    layer_id="layer-fx",
                    type=LayerType.FX_OVERLAY,
                    image_ref="artifacts/example/composite.png",
                    z_index=100,
                    order=1,
                ),
            ]
        ),
        goal=Goal(
            goal_type=GoalType.RELATION,
            constraint_struct={},
            answer_form=AnswerForm.REGION_SELECT,
        ),
        answer=Answer(answer_region_ids=["r1"], uniqueness_intent=True),
        verification=VerificationBundle(
            logical=VerificationResult(score=1.0, pass_=True, signals={}),
            perception=VerificationResult(score=0.9, pass_=True, signals={}),
            final=FinalVerification(total_score=0.95, pass_=True, failure_reason=""),
        ),
        difficulty=Difficulty(estimated_score=0.1, source="rule_based"),
    )


def test_artifact_and_report_writer_keep_same_verification_payload(
    tmp_path: Path,
) -> None:
    scene = _build_scene()
    store = LocalArtifactStoreAdapter(artifacts_root=str(tmp_path / "artifacts"))
    writer = JsonReportWriterAdapter()

    saved_dir = store.save_scene_bundle(scene)
    initial = json.loads((saved_dir / "verification.json").read_text(encoding="utf-8"))

    writer.write_verification_report(saved_dir=saved_dir, scene=scene)
    updated = json.loads((saved_dir / "verification.json").read_text(encoding="utf-8"))

    assert initial == updated
    assert set(updated.keys()) == {"scene_id", "version_id", "status", "verification"}
