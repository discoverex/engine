from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from discoverex.application.use_cases.gen_verify import orchestrator
from discoverex.application.use_cases.gen_verify.types import PromptStageRecord


class _FakeModel:
    def __init__(self, name: str, events: list[str]) -> None:
        self._name = name
        self._events = events

    def load(self, _version: str) -> str:
        self._events.append(f"load:{self._name}")
        return f"{self._name}-handle"

    def unload(self) -> None:
        self._events.append(f"unload:{self._name}")

    def predict(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


def test_run_unloads_models_between_generation_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    scene = SimpleNamespace(
        regions=[SimpleNamespace(region_id="r1", role=SimpleNamespace(value="answer"))],
        composite=SimpleNamespace(final_image_ref=""),
        meta=SimpleNamespace(
            updated_at=None, scene_id="scene-1", version_id="v1", status="ok"
        ),
        layers=SimpleNamespace(items=[]),
    )
    background = SimpleNamespace(
        asset_ref=str(tmp_path / "bg.png"),
        width=512,
        height=512,
        metadata={},
    )
    monkeypatch.setattr(
        orchestrator,
        "build_background_from_inputs",
        lambda **_: (
            background,
            PromptStageRecord(mode="prompt", prompt="bookshop"),
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "generate_region_objects",
        lambda **_: {
            "r1": SimpleNamespace(
                candidate_ref=str(tmp_path / "candidate.png"),
                object_ref=str(tmp_path / "object.png"),
                object_mask_ref=str(tmp_path / "mask.png"),
            )
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "generate_regions",
        lambda **_: (scene.regions, []),
    )
    monkeypatch.setattr(orchestrator, "build_scene", lambda **_: scene)
    monkeypatch.setattr(
        orchestrator,
        "compose_scene",
        lambda **_: SimpleNamespace(image_ref="final.png", artifact_path=None),
    )
    monkeypatch.setattr(orchestrator, "_finalize_layers", lambda **_: None)
    monkeypatch.setattr(orchestrator, "verify_scene", lambda **_: None)
    monkeypatch.setattr(
        orchestrator, "save_prompt_bundle", lambda *_: Path("prompt_bundle.json")
    )
    monkeypatch.setattr(orchestrator, "save_scene", lambda **_: tmp_path)
    monkeypatch.setattr(orchestrator, "write_verification_report", lambda **_: None)
    monkeypatch.setattr(orchestrator, "write_naturalness_report", lambda **_: None)
    monkeypatch.setattr(orchestrator, "track_run", lambda **_: None)
    monkeypatch.setattr(orchestrator, "build_prompt_tracking_params", lambda *_: {})
    monkeypatch.setattr(
        orchestrator,
        "generate_run_ids",
        lambda: SimpleNamespace(scene_id="scene-1", version_id="v1"),
    )

    context = SimpleNamespace(
        runtime=SimpleNamespace(width=512, height=512),
        model_versions=SimpleNamespace(
            background_generator="bg-v1",
            object_generator="object-v1",
            hidden_region="hidden-v1",
            inpaint="inpaint-v1",
            perception="perception-v1",
            fx="fx-v1",
            model_dump=lambda mode="python": {},
        ),
        artifacts_root=tmp_path,
        background_generator_model=_FakeModel("background", events),
        object_generator_model=_FakeModel("object", events),
        hidden_region_model=_FakeModel("hidden", events),
        inpaint_model=_FakeModel("inpaint", events),
        fx_model=_FakeModel("fx", events),
        perception_model=_FakeModel("perception", events),
        thresholds=SimpleNamespace(),
    )

    result = orchestrator.run(
        context=context,
        background_asset_ref=None,
        background_prompt="bookshop",
        object_prompt="key",
        final_prompt="final",
    )

    assert result.meta.scene_id == scene.meta.scene_id
    assert events == [
        "load:background",
        "unload:background",
        "load:hidden",
        "unload:hidden",
        "load:object",
        "unload:object",
        "load:inpaint",
        "unload:inpaint",
        "load:fx",
        "unload:fx",
        "load:perception",
        "unload:perception",
    ]


def test_run_keeps_background_generator_loaded_through_hires(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    scene = SimpleNamespace(
        regions=[],
        composite=SimpleNamespace(final_image_ref=""),
        meta=SimpleNamespace(
            updated_at=None, scene_id="scene-1", version_id="v1", status="ok"
        ),
        layers=SimpleNamespace(items=[]),
    )
    background = SimpleNamespace(
        asset_ref=str(tmp_path / "bg.png"),
        width=512,
        height=512,
        metadata={},
    )
    monkeypatch.setattr(
        orchestrator,
        "build_background_from_inputs",
        lambda **_: (
            background,
            PromptStageRecord(mode="prompt", prompt="bookshop"),
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "apply_background_canvas_upscale_if_needed",
        lambda **kwargs: kwargs["background"],
    )
    monkeypatch.setattr(
        orchestrator,
        "apply_background_detail_reconstruction_if_needed",
        lambda **kwargs: kwargs["background"],
    )
    monkeypatch.setattr(orchestrator, "_materialize_background_asset", lambda **_: None)
    monkeypatch.setattr(orchestrator, "build_candidate_regions", lambda *_: [])
    monkeypatch.setattr(orchestrator, "generate_region_objects", lambda **_: {})
    monkeypatch.setattr(orchestrator, "generate_regions", lambda **_: ([], []))
    monkeypatch.setattr(orchestrator, "build_scene", lambda **_: scene)
    monkeypatch.setattr(
        orchestrator,
        "compose_scene",
        lambda **_: SimpleNamespace(image_ref="final.png", artifact_path=None),
    )
    monkeypatch.setattr(orchestrator, "_finalize_layers", lambda **_: None)
    monkeypatch.setattr(orchestrator, "verify_scene", lambda **_: None)
    monkeypatch.setattr(
        orchestrator, "save_prompt_bundle", lambda *_: Path("prompt_bundle.json")
    )
    monkeypatch.setattr(orchestrator, "save_scene", lambda **_: tmp_path)
    monkeypatch.setattr(orchestrator, "write_verification_report", lambda **_: None)
    monkeypatch.setattr(orchestrator, "write_naturalness_report", lambda **_: None)
    monkeypatch.setattr(orchestrator, "track_run", lambda **_: None)
    monkeypatch.setattr(orchestrator, "build_prompt_tracking_params", lambda *_: {})
    monkeypatch.setattr(
        orchestrator,
        "generate_run_ids",
        lambda: SimpleNamespace(scene_id="scene-1", version_id="v1"),
    )

    context = SimpleNamespace(
        runtime=SimpleNamespace(
            width=512, height=512, background_upscale_mode="hires"
        ),
        model_versions=SimpleNamespace(
            background_generator="bg-v1",
            background_upscaler="up-v1",
            object_generator="object-v1",
            hidden_region="hidden-v1",
            inpaint="inpaint-v1",
            perception="perception-v1",
            fx="fx-v1",
            model_dump=lambda mode="python": {},
        ),
        artifacts_root=tmp_path,
        background_generator_model=_FakeModel("background", events),
        background_upscaler_model=_FakeModel("upscaler", events),
        object_generator_model=_FakeModel("object", events),
        hidden_region_model=_FakeModel("hidden", events),
        inpaint_model=_FakeModel("inpaint", events),
        fx_model=_FakeModel("fx", events),
        perception_model=_FakeModel("perception", events),
        thresholds=SimpleNamespace(),
    )

    orchestrator.run(
        context=context,
        background_asset_ref=None,
        background_prompt="bookshop",
        object_prompt="key",
        final_prompt="final",
    )

    assert events[:4] == [
        "load:background",
        "load:upscaler",
        "unload:upscaler",
        "unload:background",
    ]
