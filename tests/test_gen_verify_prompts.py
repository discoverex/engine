from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from zipfile import ZipFile

from PIL import Image

from discoverex.application.use_cases import run_gen_verify
from discoverex.application.use_cases.gen_verify.object_pipeline import (
    GeneratedObjectAsset,
)
from discoverex.config import ModelVersionsConfig, RuntimeConfig, ThresholdsConfig
from discoverex.domain.region import Region
from discoverex.domain.scene import Scene
from discoverex.models.types import ModelHandle


class _HiddenRegionModel:
    def load(self, version: str) -> ModelHandle:
        return ModelHandle(name="hidden", version=version, runtime="dummy")

    def predict(
        self, _handle: ModelHandle, _request: Any
    ) -> list[tuple[float, float, float, float]]:
        return [(10.0, 20.0, 30.0, 40.0)]


class _InpaintModel:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def load(self, version: str) -> ModelHandle:
        return ModelHandle(name="inpaint", version=version, runtime="dummy")

    def predict(self, _handle: ModelHandle, request: Any) -> dict[str, object]:
        self.requests.append(request)
        output_path = Path(str(request.output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path = output_path.with_suffix(".patch.png")
        Image.new("RGBA", (64, 64), color=(255, 0, 0, 255)).save(patch_path)
        Image.new("RGBA", (64, 64), color=(0, 128, 255, 255)).save(output_path)
        return {
            "region_id": request.region_id,
            "patch_image_ref": str(patch_path),
            "composited_image_ref": str(output_path),
        }


class _PerceptionModel:
    def load(self, version: str) -> ModelHandle:
        return ModelHandle(name="perception", version=version, runtime="dummy")

    def predict(self, _handle: ModelHandle, _request: Any) -> dict[str, float]:
        return {"confidence": 0.9}


class _FxModel:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def load(self, version: str) -> ModelHandle:
        return ModelHandle(name="fx", version=version, runtime="dummy")

    def predict(self, _handle: ModelHandle, request: Any) -> dict[str, str]:
        self.requests.append(request)
        output_path = Path(str(request.params["output_path"]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (64, 64), color=(0, 0, 0, 255)).save(output_path)
        return {"output_path": str(output_path)}


class _ObjectGeneratorModel(_FxModel):
    pass


class _ArtifactStore:
    def save_scene_bundle(self, scene: Scene) -> Path:
        scene_root = Path(scene.composite.final_image_ref).parent.parent
        metadata_dir = scene_root / "metadata"
        outputs_dir = scene_root / "outputs"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir.mkdir(parents=True, exist_ok=True)
        (metadata_dir / "scene.json").write_text(
            scene.model_dump_json(by_alias=True),
            encoding="utf-8",
        )
        (metadata_dir / "verification.json").write_text("{}", encoding="utf-8")
        (outputs_dir / "manifest.json").write_text("{}", encoding="utf-8")
        return metadata_dir


class _MetadataStore:
    def upsert_scene_metadata(self, scene: Scene) -> None:  # noqa: ARG002
        return None


class _Tracker:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def log_pipeline_run(
        self,
        run_name: str,
        params: dict[str, object],
        metrics: dict[str, float],
        artifacts: list[Path],
    ) -> None:
        self.calls.append(
            {
                "run_name": run_name,
                "params": params,
                "metrics": metrics,
                "artifacts": artifacts,
            }
        )


def _tracker_call_value(
    tracker: _Tracker,
    *,
    index: int = 0,
) -> dict[str, object]:
    return tracker.calls[index]


class _SceneIO:
    pass


class _ReportWriter:
    def write_verification_report(self, saved_dir: Path, scene: Scene) -> Path:  # noqa: ARG002
        path = saved_dir / "verification.json"
        path.write_text("{}", encoding="utf-8")
        return path


def _fake_generated_objects(
    *,
    regions: list[Region],
    candidate_path: Path,
    object_path: Path,
    mask_path: Path,
) -> dict[str, GeneratedObjectAsset]:
    region = regions[0]
    return {
        region.region_id: GeneratedObjectAsset(
            region_id=region.region_id,
            candidate_ref=str(candidate_path),
            object_ref=str(object_path),
            object_mask_ref=str(mask_path),
            width=64,
            height=64,
        )
    }


def test_run_gen_verify_writes_prompt_bundle_and_tracks_prompt_params(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    fx_model = _FxModel()
    object_model = _ObjectGeneratorModel()
    inpaint_model = _InpaintModel()
    tracker = _Tracker()
    candidate_path = tmp_path / "generated-object.candidate.png"
    object_path = tmp_path / "generated-object.object.png"
    mask_path = tmp_path / "generated-object.mask.png"
    Image.new("RGBA", (64, 64), color=(128, 0, 128, 255)).save(candidate_path)
    Image.new("RGBA", (64, 64), color=(255, 255, 0, 255)).save(object_path)
    Image.new("L", (64, 64), color=255).save(mask_path)
    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.orchestrator.generate_region_objects",
        lambda **kwargs: _fake_generated_objects(
            regions=kwargs["regions"],
            candidate_path=candidate_path,
            object_path=object_path,
            mask_path=mask_path,
        ),
    )
    context = SimpleNamespace(
        background_generator_model=fx_model,
        object_generator_model=object_model,
        hidden_region_model=_HiddenRegionModel(),
        inpaint_model=inpaint_model,
        perception_model=_PerceptionModel(),
        fx_model=fx_model,
        artifact_store=_ArtifactStore(),
        metadata_store=_MetadataStore(),
        tracker=tracker,
        scene_io=_SceneIO(),
        report_writer=_ReportWriter(),
        artifacts_root=tmp_path,
        runtime=RuntimeConfig(width=64, height=64),
        thresholds=ThresholdsConfig(
            logical_pass=0.7,
            perception_pass=0.7,
            final_pass=0.75,
        ),
        model_versions=ModelVersionsConfig(),
        settings=SimpleNamespace(
            execution=SimpleNamespace(
                flow_run_id="test-flow-run",
                flow_run_name="test-flow-name",
            )
        ),
    )

    scene = run_gen_verify(
        background_asset_ref=None,
        context=context,
        background_prompt="sunlit courtyard",
        object_prompt="hidden brass key",
        object_negative_prompt="blurry",
        final_prompt="polished playable scene",
    )

    scene_dir = tmp_path / "scenes" / scene.meta.scene_id / scene.meta.version_id
    prompt_bundle = json.loads(
        (scene_dir / "metadata" / "prompt_bundle.json").read_text(encoding="utf-8")
    )

    assert prompt_bundle["input_mode"] == "prompt"
    assert prompt_bundle["background"]["prompt"] == "sunlit courtyard"
    assert prompt_bundle["object"]["prompt"] == "hidden brass key"
    assert prompt_bundle["final_fx"]["prompt"] == "polished playable scene"
    assert prompt_bundle["regions"][0]["generation_prompt"] == "hidden brass key"
    output_manifest = json.loads(
        (scene_dir / "outputs" / "manifest.json").read_text(encoding="utf-8")
    )
    lottie_path = scene_dir / "outputs" / "objects" / "object_01.lottie"
    output_objects_dir = scene_dir / "outputs" / "objects"
    tracker_call = _tracker_call_value(tracker)
    tracker_params = cast(dict[str, object], tracker_call["params"])
    tracker_artifacts = cast(list[Path], tracker_call["artifacts"])

    assert tracker_params["background_prompt_used"] == "sunlit courtyard"
    assert tracker_params["object_prompt_used"] == "hidden brass key"
    assert tracker_params["final_prompt_used"] == "polished playable scene"
    artifact_names = {path.name for path in tracker_artifacts}
    assert "prompt_bundle.json" in artifact_names
    assert "object_01.lottie" in artifact_names
    assert "manifest.json" in artifact_names
    assert lottie_path.exists()
    assert output_objects_dir.exists()
    assert output_manifest["background_img"]["src"] == "background.png"
    assert output_manifest["answers"]
    assert output_manifest["original"]
    assert output_manifest["answers"][0]["lottie_id"] == "lottie_01"
    assert output_manifest["answers"][0]["order"] == 1
    assert (scene_dir / "outputs" / "original").exists()
    with ZipFile(lottie_path) as archive:
        names = set(archive.namelist())
        animation = json.loads(archive.read("animations/object_01.json").decode("utf-8"))
    assert "manifest.json" in names
    assert "animations/object_01.json" in names
    assert any(name.startswith("images/") for name in names)
    assert animation["metadata"]["bbox"] == {"x": 10.0, "y": 20.0, "w": 30.0, "h": 40.0}
    assert animation["layers"][0]["nm"] == "object 1"
    fx_request = cast(SimpleNamespace, fx_model.requests[0])
    inpaint_request = cast(SimpleNamespace, inpaint_model.requests[0])
    assert fx_request.mode == "background"
    assert inpaint_request.generation_prompt == "hidden brass key"
    assert str(inpaint_request.object_image_ref) == str(object_path)
    assert str(inpaint_request.object_mask_ref) == str(mask_path)
