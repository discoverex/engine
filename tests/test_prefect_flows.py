from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from discoverex.flows.prefect_flows import engine_run_flow

run_engine_job_module = importlib.import_module(
    "discoverex.application.flows.run_engine_job"
)


def test_engine_run_flow_executes_engine_job_directly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.chdir(tmp_path)

    def fake_run_engine_entry(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(run_engine_job_module, "run_engine_entry", fake_run_engine_entry)

    payload = engine_run_flow.fn(
        job_spec_json=json.dumps(
            {
                "run_mode": "inline",
                "engine": "discoverex",
                "entrypoint": [
                    "/bin/sh",
                    "-lc",
                    "PYTHONPATH=src python -m discoverex.adapters.outbound.execution.launcher",
                ],
                "engine_run": {
                    "contract_version": "v2",
                    "command": "generate",
                    "args": {"background_asset_ref": "bg://dummy"},
                },
            },
            ensure_ascii=True,
        )
    )

    assert captured["command"] == "generate"
    assert captured["config_name"] == "generate"
    assert payload["ok"] is True
    assert payload["preparation"]["mode"] == "worker"
