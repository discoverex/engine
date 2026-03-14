from __future__ import annotations

import builtins
import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import discoverex.application.flows.engine_entry as engine


def test_engine_entry_module_import_is_lazy_for_hydra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__
    prior_hydra = sys.modules.pop("hydra", None)
    prior_omegaconf = sys.modules.pop("omegaconf", None)

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("hydra") or name.startswith("omegaconf"):
            raise AssertionError(f"unexpected eager import: {name}")
        return original_import(name, *args, **kwargs)

    try:
        monkeypatch.setattr(builtins, "__import__", guarded_import)
        sys.modules.pop("discoverex.application.flows.engine_entry", None)
        module = importlib.import_module("discoverex.application.flows.engine_entry")

        assert callable(module.run_engine_entry)
        assert "hydra" not in sys.modules
        assert "omegaconf" not in sys.modules
    finally:
        if prior_hydra is not None:
            sys.modules["hydra"] = prior_hydra
        if prior_omegaconf is not None:
            sys.modules["omegaconf"] = prior_omegaconf


def test_engine_entry_flow_returns_canonical_error_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_cfg = SimpleNamespace(
        flows=SimpleNamespace(),
        runtime=SimpleNamespace(artifacts_root="artifacts/test-engine"),
        model_dump=lambda mode="python": {
            "runtime": {
                "config_version": "config-v1",
                "model_runtime": {"device": "cpu", "precision": "fp32"},
                "env": {"tracking_uri": "sqlite:///mlflow.db"},
            },
            "adapters": {
                "artifact_store": {"target": "discoverex.adapters.ArtifactStore"},
                "tracker": {"target": "discoverex.adapters.Tracker"},
            },
            "models": {
                "background_generator": {"target": "discoverex.models.Background"},
                "hidden_region": {"target": "discoverex.models.Hidden"},
                "inpaint": {"target": "discoverex.models.Inpaint"},
                "perception": {"target": "discoverex.models.Perception"},
                "fx": {"target": "discoverex.models.Fx"},
            },
        },
    )

    def _fake_load_pipeline_config(**_kwargs: Any) -> object:
        return fake_cfg

    def _failing_subflow(**_kwargs: Any) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "load_pipeline_config", _fake_load_pipeline_config)
    monkeypatch.setattr(
        engine, "_resolve_subflow", lambda *_args, **_kwargs: _failing_subflow
    )

    out = engine.engine_entry_flow(
        command="verify",
        args={"scene_json": "/tmp/s.json"},
        config_name="verify",
    )

    assert out["status"] == "failed"
    assert out["scene_json"] == "/tmp/s.json"
    assert out["metadata"]["command"] == "verify"
    assert out["metadata"]["error_type"] == "RuntimeError"
    assert out["execution_config"].endswith("resolved_execution_config.json")
    assert Path(out["execution_config"]).exists()


def test_subflows_import_without_repo_root_on_syspath(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import discoverex.flows.subflows as subflows; "
                "assert callable(subflows.generate_v1_compat)"
            ),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
