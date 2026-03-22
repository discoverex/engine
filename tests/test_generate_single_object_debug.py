from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from discoverex.application.use_cases.generate_single_object_debug import run
from discoverex.application.use_cases.gen_verify.objects.types import GeneratedObjectAsset
from discoverex.config_loader import load_pipeline_config


def test_single_object_debug_flow_config_loads() -> None:
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["flows/generate=single_object_debug"],
    )
    assert cfg.flows is not None
    assert cfg.flows.generate.target.endswith("generate_single_object_debug")


def test_single_object_debug_run_writes_debug_exports_and_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    candidate_path = tmp_path / "source" / "candidate.png"
    sam_object_path = tmp_path / "source" / "sam.object.png"
    raw_alpha_path = tmp_path / "source" / "raw-alpha.png"
    processed_object_path = tmp_path / "source" / "processed.object.png"
    processed_mask_path = tmp_path / "source" / "processed.mask.png"

    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), color=(10, 20, 30, 128)).save(candidate_path)
    Image.new("RGBA", (8, 8), color=(10, 20, 30, 255)).save(sam_object_path)
    Image.new("L", (8, 8), color=128).save(raw_alpha_path)
    Image.new("RGBA", (6, 6), color=(40, 50, 60, 255)).save(processed_object_path)
    Image.new("L", (6, 6), color=255).save(processed_mask_path)

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_single_object_debug.generate_region_objects",
        lambda **kwargs: {
            kwargs["regions"][0].region_id: GeneratedObjectAsset(
                region_id=kwargs["regions"][0].region_id,
                candidate_ref=str(candidate_path),
                object_ref=str(processed_object_path),
                object_mask_ref=str(processed_mask_path),
                width=6,
                height=6,
                raw_alpha_mask_ref=str(raw_alpha_path),
                sam_object_ref=str(sam_object_path),
                mask_source="raw_alpha_plus_sam",
            )
        },
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_single_object_debug.unload_model",
        lambda model: None,
    )

    captured_artifacts: list[tuple[str, Path | None]] = []
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_single_object_debug.write_worker_artifact_manifest",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_single_object_debug.collect_worker_artifacts",
        lambda saved_dir_arg, artifacts: captured_artifacts.extend(artifacts)
        or [(name, path.resolve()) for name, path in artifacts if path is not None],
    )

    context = SimpleNamespace(
        artifacts_root=tmp_path / "artifacts",
        object_generator_model=SimpleNamespace(load=lambda version: SimpleNamespace(model_id="realvisxl5")),
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
        overrides=["flows/generate=single_object_debug"],
    )

    result = run(
        args={"object_prompt": "antique brass key", "object_generation_size": 512},
        config=cfg,
        context=context,
    )

    output_dir = Path(result["output_dir"])
    manifest_path = Path(result["output_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    export_keys = {item["export_key"] for item in manifest["exports"]}
    logical_names = [name for name, _ in captured_artifacts]

    assert result["object_count"] == 1
    assert export_keys == {
        "rgb_preview",
        "alpha_mask",
        "final_rgba",
        "pre_sam_rgba",
        "sam_object",
        "raw_alpha_mask",
        "processed_object",
        "processed_mask",
    }
    assert (output_dir / "outputs" / "original").exists()
    assert "debug_rgb_preview" in logical_names
    assert "debug_alpha_mask" in logical_names
    assert "debug_final_rgba" in logical_names
    assert "debug_pre_sam_rgba" in logical_names
    assert "debug_sam_object" in logical_names
    assert "debug_processed_object" in logical_names
    assert "debug_processed_mask" in logical_names
    assert "output_manifest" in logical_names
