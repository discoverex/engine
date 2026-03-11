from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
register_job = importlib.import_module("register_orchestrator_job")


def test_submit_job_spec_resolves_deployment_from_engine_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(register_job, "_find_deployment_id", lambda *_args: "dep-123")
    monkeypatch.setattr(
        register_job,
        "_create_flow_run",
        lambda *_args: {"id": "flow-456", "name": "run-789"},
    )

    output = register_job.submit_job_spec(
        job_spec={
            "run_mode": "inline",
            "engine": "discoverex",
            "entrypoint": ["/bin/sh", "-lc", "python -m discoverex.orchestrator_contract.launcher"],
            "engine_run": {
                "contract_version": "v2",
                "command": "generate",
                "config_name": "generate",
                "args": {"background_asset_ref": "bg://dummy"},
                "overrides": [],
                "runtime": {"extras": ["tracking"]},
            },
            "env": {},
            "outputs_prefix": None,
            "job_name": "generate--generate--none",
        },
        prefect_api_url="http://127.0.0.1:4200/api",
    )

    assert output["deployment"] == "discoverex-generate--generate"
    assert output["flow_run_id"] == "flow-456"
    assert output["flow_run_name"] == "run-789"
