from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from discoverex.application.use_cases.generate_object_only import (
    _resolve_object_count,
    run,
)
from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
from discoverex.config_loader import load_pipeline_config


def test_object_only_flow_config_loads() -> None:
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["flows/generate=object_only"],
    )
    assert cfg.flows is not None
    assert cfg.flows.generate.target.endswith("generate_object_only")


def test_resolve_object_count_uses_prompt_count_when_present() -> None:
    assert (
        _resolve_object_count(
            {
                "object_prompt": "butterfly | antique brass key | crystal wine glass",
                "object_count": 1,
            }
        )
        == 3
    )


def test_resolve_object_count_falls_back_to_object_count_when_prompt_missing() -> None:
    assert _resolve_object_count({"object_prompt": "", "object_count": 3}) == 3


def test_object_only_passes_generate_verify_v2_style_object_args(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_generation: dict[str, object] = {}

    def fake_generate_region_objects(**kwargs):
        captured_generation.update(kwargs)
        return {
            region.region_id: GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=str(tmp_path / f"{region.region_id}.candidate.png"),
                object_ref=str(tmp_path / f"{region.region_id}.object.png"),
                object_mask_ref=str(tmp_path / f"{region.region_id}.mask.png"),
                raw_alpha_mask_ref=str(tmp_path / f"{region.region_id}.raw-alpha.png"),
                width=32,
                height=32,
                object_prompt=str(kwargs["object_prompt"]),
                object_negative_prompt=str(kwargs["object_negative_prompt"]),
            )
            for region in kwargs["regions"]
        }

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_object_only.generate_region_objects",
        fake_generate_region_objects,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_object_only.unload_model",
        lambda model: None,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_object_only.write_worker_artifact_manifest",
        lambda **kwargs: None,
    )

    context = SimpleNamespace(
        artifacts_root=tmp_path / "artifacts",
        object_generator_model=SimpleNamespace(
            load=lambda version: SimpleNamespace(model_id=version),
        ),
        model_versions=SimpleNamespace(object_generator="object-generator-v0"),
        settings=SimpleNamespace(
            tracking=SimpleNamespace(uri="mlflow://tracking"),
            execution=SimpleNamespace(flow_run_id="flow-run-1"),
        ),
        tracking_run_id=None,
    )
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["flows/generate=object_only"],
    )

    result = run(
        args={
            "object_prompt": "butterfly | antique brass key | crystal wine glass",
            "object_negative_prompt": "blurry, low quality, artifact",
            "object_base_prompt": "isolated single object on a transparent background",
            "object_base_negative_prompt": "opaque background, solid background",
            "object_generation_size": 640,
            "object_count": 1,
        },
        config=cfg,
        context=context,
    )

    assert result["object_count"] == 3
    assert len(result["generated_objects"]) == 3
    assert len(captured_generation["regions"]) == 3
    assert (
        captured_generation["object_base_prompt"]
        == "isolated single object on a transparent background"
    )
    assert (
        captured_generation["object_base_negative_prompt"]
        == "opaque background, solid background"
    )
    assert captured_generation["object_generation_size"] == 640


def test_object_only_uses_prompt_count_over_object_count(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_regions: list[object] = []

    def fake_generate_region_objects(**kwargs):
        captured_regions.extend(kwargs["regions"])
        return {
            region.region_id: GeneratedObjectAsset(
                region_id=region.region_id,
                candidate_ref=str(tmp_path / f"{region.region_id}.candidate.png"),
                object_ref=str(tmp_path / f"{region.region_id}.object.png"),
                object_mask_ref=str(tmp_path / f"{region.region_id}.mask.png"),
                width=32,
                height=32,
            )
            for region in kwargs["regions"]
        }

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_object_only.generate_region_objects",
        fake_generate_region_objects,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_object_only.unload_model",
        lambda model: None,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_object_only.write_worker_artifact_manifest",
        lambda **kwargs: None,
    )

    context = SimpleNamespace(
        artifacts_root=tmp_path / "artifacts",
        object_generator_model=SimpleNamespace(
            load=lambda version: SimpleNamespace(model_id=version),
        ),
        model_versions=SimpleNamespace(object_generator="object-generator-v0"),
        settings=SimpleNamespace(
            tracking=SimpleNamespace(uri="mlflow://tracking"),
            execution=SimpleNamespace(flow_run_id="flow-run-1"),
        ),
        tracking_run_id=None,
    )
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["flows/generate=object_only"],
    )

    result = run(
        args={
            "object_prompt": "butterfly | antique brass key",
            "object_count": 5,
        },
        config=cfg,
        context=context,
    )

    assert result["object_count"] == 2
    assert len(captured_regions) == 2
