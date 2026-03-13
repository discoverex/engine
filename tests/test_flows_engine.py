from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import discoverex.application.flows.engine_entry as engine


def test_engine_entry_flow_returns_canonical_error_payload(monkeypatch) -> None:  # type: ignore[no-untyped-def]
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

    def _fake_load_pipeline_config(**_kwargs):  # type: ignore[no-untyped-def]
        return fake_cfg

    def _failing_subflow(**_kwargs):  # type: ignore[no-untyped-def]
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
