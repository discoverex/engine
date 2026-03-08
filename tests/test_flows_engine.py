from __future__ import annotations

from types import SimpleNamespace

import discoverex.flows.engine as engine


def test_engine_entry_flow_returns_canonical_error_payload(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake_cfg = SimpleNamespace(flows=SimpleNamespace())

    def _fake_load_pipeline_config(**_kwargs):  # type: ignore[no-untyped-def]
        return fake_cfg

    def _failing_subflow(**_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "load_pipeline_config", _fake_load_pipeline_config)
    monkeypatch.setattr(engine, "_resolve_subflow", lambda *_args, **_kwargs: _failing_subflow)

    out = engine.engine_entry_flow(
        command="verify",
        args={"scene_json": "/tmp/s.json"},
        config_name="verify",
    )

    assert out["status"] == "failed"
    assert out["scene_json"] == "/tmp/s.json"
    assert out["metadata"]["command"] == "verify"
    assert out["metadata"]["error_type"] == "RuntimeError"
