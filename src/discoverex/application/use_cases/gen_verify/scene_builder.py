from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from discoverex.config import RuntimeConfig
from discoverex.domain.goal import AnswerForm, Goal, GoalType
from discoverex.domain.region import Region
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

from .types import RunIds


def generate_run_ids() -> RunIds:
    return RunIds(
        scene_id=f"scene-{uuid4().hex[:12]}",
        version_id=f"v-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        pipeline_run_id=f"run-{uuid4().hex[:12]}",
    )


def build_background(asset_ref: str, runtime_cfg: RuntimeConfig) -> Background:
    return Background(
        asset_ref=asset_ref,
        width=int(runtime_cfg.width),
        height=int(runtime_cfg.height),
    )


def build_scene(
    *,
    background: Background,
    regions: list[Region],
    model_versions: dict[str, str],
    runtime_cfg: RuntimeConfig,
    run_ids: RunIds,
) -> Scene:
    answer_ids = [regions[0].region_id] if regions else []
    now = datetime.now(timezone.utc)
    return Scene(
        meta=SceneMeta(
            scene_id=run_ids.scene_id,
            version_id=run_ids.version_id,
            status=SceneStatus.CANDIDATE,
            pipeline_run_id=run_ids.pipeline_run_id,
            model_versions=model_versions,
            config_version=str(runtime_cfg.config_version),
            created_at=now,
            updated_at=now,
        ),
        background=background,
        regions=regions,
        composite=Composite(final_image_ref=""),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id=f"layer-base-{run_ids.scene_id}",
                    type=LayerType.BASE,
                    image_ref=background.asset_ref,
                    z_index=0,
                    order=0,
                )
            ]
        ),
        goal=Goal(
            goal_type=GoalType.RELATION,
            constraint_struct={
                "description": "select target region based on relation template"
            },
            scope_region_ids=[r.region_id for r in regions],
            answer_form=AnswerForm.REGION_SELECT,
        ),
        answer=Answer(answer_region_ids=answer_ids, uniqueness_intent=True),
        verification=VerificationBundle(
            logical=VerificationResult(score=0.0, pass_=False, signals={}),
            perception=VerificationResult(score=0.0, pass_=False, signals={}),
            final=FinalVerification(
                total_score=0.0,
                pass_=False,
                failure_reason="not_verified",
            ),
        ),
        difficulty=Difficulty(estimated_score=0.0, source="rule_based"),
    )
