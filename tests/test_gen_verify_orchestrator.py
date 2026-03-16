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
        meta=SimpleNamespace(updated_at=None, scene_id="scene-1", version_id="v1", status="ok"),
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
    monkeypatch.setattr(orchestrator, "save_prompt_bundle", lambda *_: Path("prompt_bundle.json"))
    monkeypatch.setattr(orchestrator, "save_scene", lambda **_: tmp_path)
    monkeypatch.setattr(orchestrator, "write_verification_report", lambda **_: None)
    monkeypatch.setattr(orchestrator, "track_run", lambda **_: None)
    monkeypatch.setattr(orchestrator, "build_prompt_tracking_params", lambda *_: {})
    monkeypatch.setattr(orchestrator, "generate_run_ids", lambda: SimpleNamespace(scene_id="scene-1", version_id="v1"))

    context = SimpleNamespace(
        runtime=SimpleNamespace(width=512, height=512),
        model_versions=SimpleNamespace(
            background_generator="bg-v1",
            hidden_region="hidden-v1",
            inpaint="inpaint-v1",
            perception="perception-v1",
            fx="fx-v1",
            model_dump=lambda mode="python": {},
        ),
        artifacts_root=tmp_path,
        background_generator_model=_FakeModel("background", events),
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
        "load:inpaint",
        "unload:inpaint",
        "load:fx",
        "unload:fx",
        "load:perception",
        "unload:perception",
    ]
