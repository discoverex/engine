from __future__ import annotations

import json
import sys
from pathlib import Path

from infra.ops.collect_sweep import _aggregate


def test_collect_sweep_uses_combined_adapter() -> None:
    output = _aggregate(
        [
            {
                "policy_id": "baseline",
                "scenario_id": "scene-001",
                "representative_scores": {
                    "composite_repr": 0.8,
                    "verify_repr": 0.9,
                    "naturalness_repr": 0.7,
                    "object_repr": 0.6,
                },
                "object_scores": [{"verify_score": 0.75}],
            }
        ],
        submitted_manifest=None,
        flow_run_states=None,
        collector_adapter="combined",
    )

    assert output["policy_count"] == 1
    assert output["policies"][0]["mean_composite_repr"] == 0.8


def test_collect_sweep_main_reads_case_dir_from_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    artifacts_root = tmp_path / "artifacts"
    cases_dir = artifacts_root / "experiments" / "naturalness_sweeps" / "combo" / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    (cases_dir / "case.json").write_text(
        json.dumps(
            {
                "policy_id": "baseline",
                "scenario_id": "scene-001",
                "representative_scores": {
                    "composite_repr": 0.8,
                    "verify_repr": 0.9,
                    "naturalness_repr": 0.7,
                    "object_repr": 0.6,
                },
                "object_scores": [{"verify_score": 0.75}],
            }
        ),
        encoding="utf-8",
    )
    submitted = tmp_path / "submitted.json"
    submitted.write_text(
        json.dumps(
            {
                "sweep_id": "combo",
                "case_dir_name": "naturalness_sweeps",
                "collector_adapter": "combined",
                "results": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect_sweep.py",
            "--submitted-manifest",
            str(submitted),
            "--artifacts-root",
            str(artifacts_root),
            "--output-json",
            str(tmp_path / "out.json"),
        ],
    )

    from infra.ops.collect_sweep import main

    assert main() == 0
    payload = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert payload["collector_adapter"] == "combined"
    assert payload["policy_count"] == 1
