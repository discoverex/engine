from __future__ import annotations

import json
from pathlib import Path

from infra.ops.collect_combined_sweep import _aggregate, main as collect_main


def test_aggregate_ranks_by_composite_repr() -> None:
    output = _aggregate(
        [
            {
                "policy_id": "p1",
                "representative_scores": {
                    "composite_repr": 0.82,
                    "verify_repr": 0.8,
                    "naturalness_repr": 0.7,
                    "object_repr": 0.6,
                },
                "object_scores": [{"verify_score": 0.55}],
            },
            {
                "policy_id": "p2",
                "representative_scores": {
                    "composite_repr": 0.75,
                    "verify_repr": 0.7,
                    "naturalness_repr": 0.7,
                    "object_repr": 0.7,
                },
                "object_scores": [{"verify_score": 0.65}],
            },
        ]
    )

    assert output["policies"][0]["policy_id"] == "p1"
    assert output["policies"][0]["mean_composite_repr"] == 0.82


def test_collect_combined_sweep_writes_outputs(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    cases_dir = artifacts_root / "experiments" / "naturalness_sweeps" / "combo" / "cases"
    cases_dir.mkdir(parents=True)
    (cases_dir / "case-1.json").write_text(
        json.dumps(
            {
                "policy_id": "p1",
                "representative_scores": {
                    "composite_repr": 0.8,
                    "verify_repr": 0.7,
                    "naturalness_repr": 0.8,
                    "object_repr": 0.9,
                },
                "object_scores": [{"verify_score": 0.6}],
            }
        ),
        encoding="utf-8",
    )
    output_json = tmp_path / "combined.json"
    output_csv = tmp_path / "combined.csv"

    import sys

    argv = sys.argv
    sys.argv = [
        "collect_combined_sweep.py",
        "--sweep-id",
        "combo",
        "--artifacts-root",
        str(artifacts_root),
        "--output-json",
        str(output_json),
        "--output-csv",
        str(output_csv),
    ]
    try:
        assert collect_main() == 0
    finally:
        sys.argv = argv

    assert output_json.exists()
    assert output_csv.exists()
