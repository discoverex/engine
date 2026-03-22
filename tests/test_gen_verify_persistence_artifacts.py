from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from discoverex.application.use_cases.exporting.types import OutputExportResult
from discoverex.application.use_cases.gen_verify.persistence import track_run
from discoverex.domain.goal import AnswerForm, Goal, GoalType
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


def test_track_run_includes_source_layers_and_originals_in_worker_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc)
    artifacts_root = tmp_path / "artifacts"
    saved_dir = artifacts_root / "scenes" / "scene-1" / "v1"
    metadata_dir = saved_dir / "metadata"
    outputs_dir = saved_dir / "outputs"
    metadata_dir.mkdir(parents=True)
    outputs_dir.mkdir(parents=True)

    for path in (
        metadata_dir / "scene.json",
        metadata_dir / "verification.json",
        outputs_dir / "composite.png",
        outputs_dir / "layers" / "animation.lottie",
        outputs_dir / "output_manifest.json",
        outputs_dir / "layers" / "objects" / "001-layer-object.png",
        outputs_dir / "layers" / "source-objects" / "001-layer-object.png",
        outputs_dir / "delivery" / "metadata" / "scene.json",
        outputs_dir / "delivery" / "metadata" / "verification.json",
        outputs_dir / "delivery" / "layers" / "animation.lottie",
        outputs_dir / "original" / "r1" / "object.png",
        outputs_dir / "original" / "r1" / "diagnostics.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    scene = Scene(
        meta=SceneMeta(
            scene_id="scene-1",
            version_id="v1",
            status=SceneStatus.APPROVED,
            pipeline_run_id="run-1",
            model_versions={},
            config_version="config-v1",
            created_at=now,
            updated_at=now,
        ),
        background=Background(asset_ref="", width=64, height=64, metadata={}),
        regions=[],
        composite=Composite(final_image_ref=str(outputs_dir / "composite.png")),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id="layer-base",
                    type=LayerType.BASE,
                    image_ref=str(outputs_dir / "composite.png"),
                    z_index=0,
                    order=0,
                )
            ]
        ),
        goal=Goal(
            goal_type=GoalType.RELATION,
            constraint_struct={},
            answer_form=AnswerForm.REGION_SELECT,
        ),
        answer=Answer(answer_region_ids=[], uniqueness_intent=True),
        verification=VerificationBundle(
            logical=VerificationResult(score=1.0, pass_=True, signals={}),
            perception=VerificationResult(score=1.0, pass_=True, signals={}),
            final=FinalVerification(total_score=1.0, pass_=True, failure_reason=""),
        ),
        difficulty=Difficulty(estimated_score=0.1, source="rule_based"),
    )

    exported = OutputExportResult(
        manifest_path=outputs_dir / "output_manifest.json",
        lottie_path=outputs_dir / "layers" / "animation.lottie",
        layer_paths=[outputs_dir / "layers" / "objects" / "001-layer-object.png"],
        source_layer_paths=[
            outputs_dir / "layers" / "source-objects" / "001-layer-object.png"
        ],
        original_paths=[
            outputs_dir / "original" / "r1" / "object.png",
            outputs_dir / "original" / "r1" / "diagnostics.json",
        ],
        delivery_paths=[
            outputs_dir / "delivery" / "metadata" / "scene.json",
            outputs_dir / "delivery" / "metadata" / "verification.json",
            outputs_dir / "delivery" / "layers" / "animation.lottie",
        ],
    )

    captured_artifacts: list[tuple[str, Path | None]] = []

    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.export_output_bundle",
        lambda **kwargs: exported,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.build_tracking_params",
        lambda snapshot: {},
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.apply_tracking_identity",
        lambda params, settings: params,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.tracking_run_name",
        lambda settings, default: default,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.collect_worker_artifacts",
        lambda saved_dir_arg, artifacts: captured_artifacts.extend(artifacts)
        or [(name, path.resolve()) for name, path in artifacts if path is not None],
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.write_worker_artifact_manifest",
        lambda **kwargs: None,
    )

    context = SimpleNamespace(
        artifacts_root=artifacts_root,
        settings=SimpleNamespace(),
        tracker=SimpleNamespace(log_pipeline_run=lambda **kwargs: "tracking-run-1"),
        tracking_run_id=None,
        execution_snapshot=None,
        execution_snapshot_path=None,
    )

    tracking_run_id = track_run(
        context=context,
        scene=scene,
        saved_dir=saved_dir,
        composite_artifact=outputs_dir / "composite.png",
    )

    assert tracking_run_id == "tracking-run-1"
    logical_names = [name for name, _ in captured_artifacts]
    assert "output_layer/001-layer-object.png" in logical_names
    assert "output_source_layer/001-layer-object.png" in logical_names
    assert "output_original/original/r1/object.png" in logical_names
    assert "output_original/original/r1/diagnostics.json" in logical_names
    assert "delivery/delivery/metadata/scene.json" in logical_names
    assert "delivery/delivery/metadata/verification.json" in logical_names
    assert "delivery/delivery/layers/animation.lottie" in logical_names
