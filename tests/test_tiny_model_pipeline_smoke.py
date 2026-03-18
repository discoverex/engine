from __future__ import annotations

from pathlib import Path

import pytest

from discoverex.application.use_cases import (
    run_gen_verify,
    run_replay_eval,
    run_verify_only,
)
from discoverex.config_loader import load_pipeline_config


def _run_pipeline_roundtrip(tmp_path: Path, model_group: str) -> None:
    pytest.importorskip("torch")
    pytest.importorskip("mlflow")
    if model_group == "tiny_hf":
        pytest.importorskip("transformers")

    run_dir = tmp_path / model_group
    run_dir.mkdir(parents=True, exist_ok=True)
    tracking_uri = f"sqlite:///{(run_dir / 'mlflow.db').resolve()}"

    overrides = [
        "models/background_generator=" + model_group,
        "models/hidden_region=" + model_group,
        "models/inpaint=" + model_group,
        "models/perception=" + model_group,
        "models/fx=" + model_group,
        "runtime/model_runtime=cpu",
        f"runtime.artifacts_root={run_dir / 'artifacts'}",
        f"runtime.env.tracking_uri={tracking_uri}",
    ]
    cfg = load_pipeline_config(config_name="gen_verify", overrides=overrides)

    from discoverex.bootstrap import build_context

    context = build_context(config=cfg)
    scene = run_gen_verify(background_asset_ref="bg://tiny-smoke", context=context)

    scene_json = (
        Path(cfg.runtime.artifacts_root)
        / "scenes"
        / scene.meta.scene_id
        / scene.meta.version_id
        / "metadata"
        / "scene.json"
    )
    assert scene_json.exists()

    updated = run_verify_only(scene=scene, context=context)
    assert updated.meta.scene_id == scene.meta.scene_id

    report_path = run_replay_eval(scene_json_paths=[scene_json], context=context)
    assert report_path.exists()


@pytest.mark.parametrize("model_group", ["tiny_torch", "tiny_hf"])
def test_tiny_model_groups_run_all_three_pipelines(
    tmp_path: Path,
    model_group: str,
) -> None:
    _run_pipeline_roundtrip(tmp_path=tmp_path, model_group=model_group)
