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


def test_lightning_object_generator_config_loads() -> None:
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["models/object_generator=layerdiffuse_realvisxl5_lightning"],
    )
    assert (
        cfg.models.object_generator.model_dump(mode="python")["model_id"]
        == "SG161222/RealVisXL_V5.0_Lightning"
    )
    assert (
        cfg.models.object_generator.model_dump(mode="python")["default_num_inference_steps"]
        == 5
    )
    assert (
        cfg.models.object_generator.model_dump(mode="python")["default_guidance_scale"]
        == 1.0
    )


def test_lightning_base_vae_object_generator_config_loads() -> None:
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["models/object_generator=layerdiffuse_realvisxl5_lightning_basevae"],
    )
    payload = cfg.models.object_generator.model_dump(mode="python")
    assert payload["model_id"] == "SG161222/RealVisXL_V5.0_Lightning"


def test_sd15_transparent_object_generator_config_loads() -> None:
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["models/object_generator=layerdiffuse_sd15_transparent"],
    )
    payload = cfg.models.object_generator.model_dump(mode="python")
    assert payload["model_id"] == "runwayml/stable-diffusion-v1-5"
    assert payload["pipeline_variant"] == "sd15_layerdiffuse_transparent"
    assert payload["weights_repo"] == "LayerDiffusion/layerdiffusion-v1"
    assert (
        payload["transparent_decoder_weight_name"]
        == "layer_sd15_vae_transparent_decoder.safetensors"
    )
    assert payload["attn_weight_name"] == "layer_sd15_transparent_attn.safetensors"


def test_pixart_object_generator_config_loads() -> None:
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["models/object_generator=pixart_sigma_8gb"],
    )
    payload = cfg.models.object_generator.model_dump(mode="python")
    assert payload["model_id"] == "PixArt-alpha/PixArt-Sigma-XL-2-1024-MS"
    assert payload["default_num_inference_steps"] == 20


def test_single_object_base_vae_debug_flow_config_loads() -> None:
    cfg = load_pipeline_config(
        config_name="generate",
        config_dir="conf",
        overrides=["flows/generate=single_object_base_vae_debug"],
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

    captured_generation: dict[str, object] = {}

    def _fake_generate_region_objects(**kwargs):
        captured_generation.update(kwargs)
        return {
            kwargs["regions"][0].region_id: GeneratedObjectAsset(
                region_id=kwargs["regions"][0].region_id,
                candidate_ref=str(candidate_path),
                object_ref=str(processed_object_path),
                object_mask_ref=str(processed_mask_path),
                width=6,
                height=6,
                raw_alpha_mask_ref=str(raw_alpha_path),
                sam_object_ref=str(sam_object_path),
                mask_source="layerdiffuse_alpha",
                object_prompt=str(kwargs["object_prompt"]),
                object_negative_prompt=str(kwargs["object_negative_prompt"]),
                object_model_id="SG161222/RealVisXL_V5.0_Lightning",
                object_sampler="dpmpp_sde_karras",
                object_steps=5,
                object_guidance_scale=1.5,
            )
        }

    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_single_object_debug.generate_region_objects",
        _fake_generate_region_objects,
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
    captured_tracking: dict[str, object] = {}
    tracker = SimpleNamespace(
        log_pipeline_run=lambda **kwargs: captured_tracking.update(kwargs) or "mlflow-run-1"
    )
    monkeypatch.setattr(
        "discoverex.application.use_cases.generate_single_object_debug.collect_worker_artifacts",
        lambda saved_dir_arg, artifacts: captured_artifacts.extend(artifacts)
        or [(name, path.resolve()) for name, path in artifacts if path is not None],
    )

    context = SimpleNamespace(
        artifacts_root=tmp_path / "artifacts",
        object_generator_model=SimpleNamespace(
            load=lambda version: SimpleNamespace(
                model_id="SG161222/RealVisXL_V5.0_Lightning"
            ),
            default_prompt="isolated single opaque object on a transparent background",
            sampler="dpmpp_sde_karras",
        ),
        model_versions=SimpleNamespace(object_generator="object-generator-v0"),
        settings=SimpleNamespace(
            tracking=SimpleNamespace(uri="mlflow://tracking"),
            execution=SimpleNamespace(flow_run_id="flow-run-1", flow_run_name="flow-run-name"),
        ),
        tracker=tracker,
        tracking_run_id=None,
        execution_snapshot={"command": "generate", "args": {"sweep_id": "s1"}},
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
        "base_preview",
        "alpha_mask",
        "transparent_visualization",
        "final_rgba",
        "pre_sam_rgba",
        "sam_object",
        "raw_alpha_mask",
        "processed_object",
        "processed_mask",
    }
    assert (output_dir / "outputs" / "original").exists()
    assert "debug_rgb_preview" in logical_names
    assert "debug_base_preview" in logical_names
    assert "debug_alpha_mask" in logical_names
    assert "debug_transparent_visualization" in logical_names
    assert "debug_final_rgba" in logical_names
    assert "debug_pre_sam_rgba" in logical_names
    assert "debug_sam_object" in logical_names
    assert "debug_processed_object" in logical_names
    assert "debug_processed_mask" in logical_names
    assert "output_manifest" in logical_names
    assert result["mlflow_run_id"] == "mlflow-run-1"
    assert (
        captured_generation["object_prompt"]
        == "isolated single opaque object on a transparent background, antique brass key"
    )
    assert (
        result["effective_prompt"]
        == "isolated single opaque object on a transparent background, antique brass key, isolated single object, centered composition, plain neutral backdrop, no environment, no floor"
    )
    assert captured_tracking["run_name"] == "flow-run-1"
    assert captured_tracking["params"]["prefect.flow_run_id"] == "flow-run-1"
    assert captured_tracking["params"]["prefect.flow_run_name"] == "flow-run-name"
    assert (
        captured_tracking["params"]["base_prompt"]
        == "isolated single opaque object on a transparent background"
    )
    assert (
        captured_tracking["params"]["effective_prompt"]
        == "isolated single opaque object on a transparent background, antique brass key, isolated single object, centered composition, plain neutral backdrop, no environment, no floor"
    )
    assert captured_tracking["params"]["model_id"] == "SG161222/RealVisXL_V5.0_Lightning"
    assert captured_tracking["params"]["sampler"] == "dpmpp_sde_karras"
    assert captured_tracking["params"]["num_inference_steps"] == "5"
    assert captured_tracking["params"]["guidance_scale"] == "1.5"
