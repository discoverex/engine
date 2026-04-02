from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from discoverex.application.use_cases.exporting.types import OutputExportResult
from discoverex.application.use_cases.gen_verify.persistence import (
    track_run,
    write_naturalness_report,
)
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
from discoverex.domain.region import BBox, Geometry, Region, RegionRole, RegionSource
from discoverex.domain.verification import (
    FinalVerification,
    HiddenObjectMeta,
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
        outputs_dir / "background" / "background.png",
        outputs_dir / "manifest.json",
        outputs_dir / "objects" / "object_01.png",
        outputs_dir / "objects" / "object_01.lottie",
        outputs_dir / "delivery" / "metadata" / "scene.json",
        outputs_dir / "delivery" / "metadata" / "verification.json",
        outputs_dir / "delivery" / "background" / "background.png",
        outputs_dir / "delivery" / "manifest.json",
        outputs_dir / "delivery" / "objects" / "object_01.png",
        outputs_dir / "delivery" / "objects" / "object_01.lottie",
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
        manifest_path=outputs_dir / "manifest.json",
        delivery_manifest_path=outputs_dir / "delivery" / "manifest.json",
        background_path=outputs_dir / "background" / "background.png",
        object_png_paths=[outputs_dir / "objects" / "object_01.png"],
        object_lottie_paths=[outputs_dir / "objects" / "object_01.lottie"],
        original_paths=[
            outputs_dir / "original" / "r1" / "object.png",
            outputs_dir / "original" / "r1" / "diagnostics.json",
        ],
        delivery_paths=[
            outputs_dir / "delivery" / "metadata" / "scene.json",
            outputs_dir / "delivery" / "metadata" / "verification.json",
            outputs_dir / "delivery" / "background" / "background.png",
            outputs_dir / "delivery" / "manifest.json",
            outputs_dir / "delivery" / "objects" / "object_01.png",
            outputs_dir / "delivery" / "objects" / "object_01.lottie",
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
    assert "background" in logical_names
    assert "output_object_png/object_01.png" in logical_names
    assert "output_object_lottie/object_01.lottie" in logical_names
    assert "output_original/original/r1/object.png" in logical_names
    assert "output_original/original/r1/diagnostics.json" in logical_names
    assert "delivery/delivery/metadata/scene.json" in logical_names
    assert "delivery/delivery/metadata/verification.json" in logical_names
    assert "delivery/delivery/objects/object_01.lottie" in logical_names


def test_track_run_writes_naturalness_sweep_case_result(
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
        metadata_dir / "naturalness.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    naturalness_path = metadata_dir / "naturalness.json"
    naturalness_path.write_text(
        """
{"naturalness":{"overall_score":0.81,"summary":{"avg_placement_fit":0.7,"avg_seam_visibility":0.2,"avg_saliency_lift":0.3}}}
""".strip(),
        encoding="utf-8",
    )

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
            tags=[],
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

    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.export_output_bundle",
        lambda **kwargs: OutputExportResult(
            manifest_path=outputs_dir / "manifest.json",
            delivery_manifest_path=outputs_dir / "delivery" / "manifest.json",
            background_path=outputs_dir / "background" / "background.png",
            object_png_paths=[],
            object_lottie_paths=[],
            original_paths=[],
            delivery_paths=[],
        ),
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
        lambda saved_dir_arg, artifacts: [(name, path) for name, path in artifacts if path is not None],
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.write_worker_artifact_manifest",
        lambda **kwargs: None,
    )

    context = SimpleNamespace(
        artifacts_root=artifacts_root,
        settings=SimpleNamespace(execution=SimpleNamespace(flow_run_id="flow-1")),
        tracker=SimpleNamespace(log_pipeline_run=lambda **kwargs: "tracking-run-1"),
        tracking_run_id=None,
        execution_snapshot={
            "args": {
                "sweep_id": "sweep-1",
                "policy_id": "p01",
                "scenario_id": "scene-a",
                "combo_id": "combo-001",
                "search_stage": "coarse",
                "sweep_runner_type": "combined",
                "sweep_collector_adapter": "combined",
                "sweep_artifact_namespace": "naturalness_sweeps",
                "sweep_execution_mode": "case_per_run",
            }
        },
        execution_snapshot_path=None,
    )

    track_run(
        context=context,
        scene=scene,
        saved_dir=saved_dir,
        composite_artifact=outputs_dir / "composite.png",
        naturalness_artifact=naturalness_path,
    )

    result_files = list(
        (
            artifacts_root
            / "experiments"
            / "naturalness_sweeps"
            / "sweep-1"
            / "cases"
        ).glob("*.json")
    )
    assert len(result_files) == 1
    payload = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert payload["policy_id"] == "p01"
    assert payload["scenario_id"] == "scene-a"
    assert payload["flow_run_id"] == "flow-1"
    assert payload["sweep_runner_type"] == "combined"
    assert payload["sweep_collector_adapter"] == "combined"
    assert payload["sweep_artifact_namespace"] == "naturalness_sweeps"
    assert payload["naturalness_metrics"]["naturalness.overall_score"] == 0.81


def test_write_naturalness_report_writes_to_scene_metadata_dir(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    scene_dir = tmp_path / "artifacts" / "scenes" / "scene-1" / "v1"
    metadata_dir = scene_dir / "metadata"
    outputs_dir = scene_dir / "outputs"
    metadata_dir.mkdir(parents=True)
    outputs_dir.mkdir(parents=True)
    composite_path = outputs_dir / "composite.png"
    composite_path.write_bytes(b"x")
    selected_variant_path = scene_dir / "assets" / "patches" / "variant.png"
    selected_variant_path.parent.mkdir(parents=True, exist_ok=True)
    selected_variant_path.write_bytes(b"x")

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
        background=Background(
            asset_ref=str(composite_path),
            width=64,
            height=64,
            metadata={},
        ),
        regions=[],
        composite=Composite(final_image_ref=str(composite_path)),
        layers=LayerStack(
            items=[
                LayerItem(
                    layer_id="layer-base",
                    type=LayerType.BASE,
                    image_ref=str(composite_path),
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

    path = write_naturalness_report(scene_dir, scene)

    assert path == metadata_dir / "naturalness.json"


def test_track_run_logs_full_parent_and_object_metrics(
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
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    naturalness_path = metadata_dir / "naturalness.json"
    naturalness_path.write_text("{}", encoding="utf-8")
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
            tags=[],
        ),
        background=Background(asset_ref="", width=64, height=64, metadata={}),
        regions=[
            Region(
                region_id="r-1",
                geometry=Geometry(type="bbox", bbox=BBox(x=1, y=2, w=3, h=4)),
                role=RegionRole.ANSWER,
                source=RegionSource.MANUAL,
                attributes={
                    "object_image_ref": "obj://1",
                    "verify_score": 0.42,
                    "verify_pass": True,
                    "fixture_region_id": "fixture-r-1",
                    "object_label": "red mug",
                    "generation_prompt_resolved": "red mug",
                    "object_prompt_resolved": "isolated single object on a transparent background, red mug",
                    "mask_source": "fixture",
                },
                version=1,
            )
        ],
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
            logical=VerificationResult(score=0.7, pass_=True, signals={"alpha": 0.1}),
            perception=VerificationResult(score=0.8, pass_=True, signals={"beta": 0.2}),
            final=FinalVerification(total_score=0.75, pass_=True, failure_reason=""),
            scene_difficulty=0.3,
            hidden_objects=[
                HiddenObjectMeta(
                    obj_id="r-1",
                    human_field=0.4,
                    ai_field=0.5,
                    D_obj=0.6,
                    difficulty_signals={"gamma": 0.7},
                )
            ],
        ),
        difficulty=Difficulty(estimated_score=0.1, source="rule_based"),
    )

    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.export_output_bundle",
        lambda **kwargs: OutputExportResult(
            manifest_path=outputs_dir / "manifest.json",
            delivery_manifest_path=outputs_dir / "delivery" / "manifest.json",
            background_path=outputs_dir / "background" / "background.png",
            object_png_paths=[],
            object_lottie_paths=[],
            original_paths=[],
            delivery_paths=[],
        ),
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
        lambda saved_dir_arg, artifacts: [(name, path) for name, path in artifacts if path is not None],
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence.write_worker_artifact_manifest",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence._load_naturalness_payload",
        lambda path: {
            "naturalness": {
                "overall_score": 0.9,
                "summary": {
                    "avg_placement_fit": 0.8,
                    "avg_seam_visibility": 0.2,
                    "avg_saliency_lift": 0.1,
                },
                "regions": [
                    {
                        "region_id": "r-1",
                        "natural_hidden_score": 0.91,
                        "placement_fit": 0.82,
                        "seam_visibility": 0.22,
                        "saliency_lift": 0.12,
                        "diagnosis_signals": {"delta": 0.33},
                    }
                ],
            }
        },
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.persistence._evaluate_scene_object_quality",
        lambda saved_dir_arg, scene_arg: (
            {
                "scores": [
                    {
                        "object_ref": "obj://1",
                        "mask_source": "fixture",
                        "overall_score": 0.87,
                        "subscores": {
                            "blur": 0.9,
                            "white_balance": 0.8,
                            "saturation": 0.7,
                            "contrast": 0.6,
                        },
                        "metrics": {
                            "laplacian_variance": 12.0,
                            "white_balance_error": 3.0,
                            "mean_saturation": 0.45,
                            "luma_stddev": 24.0,
                        },
                    }
                ],
                "summary": {
                    "run_score": 0.77,
                    "mean_overall_score": 0.87,
                    "min_overall_score": 0.87,
                    "min_laplacian_variance": 12.0,
                    "mean_white_balance_error": 3.0,
                    "mean_saturation": 0.45,
                    "mean_contrast": 24.0,
                },
            },
            "gallery.png",
        ),
    )

    context = SimpleNamespace(
        artifacts_root=artifacts_root,
        settings=SimpleNamespace(execution=SimpleNamespace(flow_run_id="flow-1")),
        tracker=SimpleNamespace(
            log_pipeline_run=lambda **kwargs: calls.append(kwargs) or f"tracking-{len(calls)}"
        ),
        tracking_run_id=None,
        execution_snapshot={"args": {"sweep_id": "sweep-1", "policy_id": "p01", "scenario_id": "scene-a"}},
        execution_snapshot_path=None,
    )

    track_run(
        context=context,
        scene=scene,
        saved_dir=saved_dir,
        composite_artifact=outputs_dir / "composite.png",
        naturalness_artifact=naturalness_path,
    )

    assert len(calls) == 2
    parent_metrics = calls[0]["metrics"]
    child_metrics = calls[1]["metrics"]
    assert parent_metrics["verify.logical.signals.alpha"] == 0.1
    assert parent_metrics["verify.perception.signals.beta"] == 0.2
    assert parent_metrics["object_quality.run_score"] == 0.77
    assert child_metrics["verify.human_field"] == 0.4
    assert child_metrics["verify.difficulty_signals.gamma"] == 0.7
    assert child_metrics["naturalness.diagnosis_signals.delta"] == 0.33
    assert child_metrics["object_quality.raw.laplacian_variance"] == 12.0
    child_params = calls[1]["params"]
    child_tags = calls[1]["tags"]
    assert child_params["policy.object_label"] == "red mug"
    assert child_params["policy.object_prompt"] == "red mug"
    assert child_params["policy.fixture_region_id"] == "fixture-r-1"
    assert child_tags["object_name"] == "red mug"
    assert child_tags["fixture_region_id"] == "fixture-r-1"
    assert calls[1]["run_name"] == "scene-1:red mug:r-1"
