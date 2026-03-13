from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from discoverex.application.use_cases.gen_verify.runtime_metrics import track_stage_vram


def test_track_stage_vram_records_snapshot_and_updates_file(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    snapshot = {"runtime_metrics": {}}
    path = tmp_path / "resolved_execution_config.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    context = SimpleNamespace(
        execution_snapshot=snapshot,
        execution_snapshot_path=path,
    )

    monkeypatch.setattr(
        "discoverex.application.use_cases.gen_verify.runtime_metrics._load_torch",
        lambda: None,
    )

    with track_stage_vram(context, "final_render"):
        pass

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["runtime_metrics"]["vram_peaks"]["final_render"] == {
        "device": "cpu",
        "available": False,
    }
