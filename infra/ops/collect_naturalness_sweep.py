#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and aggregate naturalness sweep case results."
    )
    parser.add_argument(
        "--submitted-manifest",
        default=None,
        help="Optional submitted.json emitted by naturalness_sweep.py",
    )
    parser.add_argument("--sweep-id", default=None)
    parser.add_argument(
        "--artifacts-root",
        default="/var/lib/discoverex/engine-runs",
    )
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-csv", default=None)
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must decode to an object")
    return payload


def _discover_cases(*, artifacts_root: Path, sweep_id: str) -> list[dict[str, Any]]:
    root = artifacts_root / "experiments" / "naturalness_sweeps" / sweep_id / "cases"
    if not root.exists():
        return []
    cases: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        payload = _load_json(path)
        payload["result_path"] = str(path)
        cases.append(payload)
    return cases


def _expected_cases(submitted_manifest: dict[str, Any] | None) -> set[tuple[str, str]]:
    if not isinstance(submitted_manifest, dict):
        return set()
    results = submitted_manifest.get("results", [])
    if not isinstance(results, list):
        return set()
    expected: set[tuple[str, str]] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        policy_id = str(item.get("policy_id", "")).strip()
        scenario_id = str(item.get("scenario_id", "")).strip()
        if policy_id and scenario_id:
            expected.add((policy_id, scenario_id))
    return expected


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        policy_id = str(case.get("policy_id", "")).strip() or "unknown"
        grouped.setdefault(policy_id, []).append(case)
    policies: list[dict[str, Any]] = []
    for policy_id, items in sorted(grouped.items()):
        overall_scores = [
            float(metrics.get("naturalness.overall_score"))
            for case in items
            if isinstance((metrics := case.get("naturalness_metrics")), dict)
            and isinstance(metrics.get("naturalness.overall_score"), (int, float))
        ]
        placement_scores = [
            float(metrics.get("naturalness.avg_placement_fit"))
            for case in items
            if isinstance((metrics := case.get("naturalness_metrics")), dict)
            and isinstance(metrics.get("naturalness.avg_placement_fit"), (int, float))
        ]
        seam_scores = [
            float(metrics.get("naturalness.avg_seam_visibility"))
            for case in items
            if isinstance((metrics := case.get("naturalness_metrics")), dict)
            and isinstance(metrics.get("naturalness.avg_seam_visibility"), (int, float))
        ]
        saliency_scores = [
            float(metrics.get("naturalness.avg_saliency_lift"))
            for case in items
            if isinstance((metrics := case.get("naturalness_metrics")), dict)
            and isinstance(metrics.get("naturalness.avg_saliency_lift"), (int, float))
        ]
        failed = [
            case for case in items if str(case.get("status", "")).strip().lower() != "completed"
        ]
        policies.append(
            {
                "policy_id": policy_id,
                "case_count": len(items),
                "completed_case_count": len(items) - len(failed),
                "failed_case_count": len(failed),
                "mean_overall_score": round(sum(overall_scores) / len(overall_scores), 4)
                if overall_scores
                else 0.0,
                "min_overall_score": round(min(overall_scores), 4) if overall_scores else 0.0,
                "mean_placement_fit": round(sum(placement_scores) / len(placement_scores), 4)
                if placement_scores
                else 0.0,
                "mean_seam_visibility": round(sum(seam_scores) / len(seam_scores), 4)
                if seam_scores
                else 0.0,
                "mean_saliency_lift": round(sum(saliency_scores) / len(saliency_scores), 4)
                if saliency_scores
                else 0.0,
                "scenario_ids": sorted(
                    {
                        str(case.get("scenario_id", "")).strip()
                        for case in items
                        if str(case.get("scenario_id", "")).strip()
                    }
                ),
            }
        )
    policies.sort(
        key=lambda item: (
            -float(item["mean_overall_score"]),
            -float(item["min_overall_score"]),
            float(item["failed_case_count"]),
            str(item["policy_id"]),
        )
    )
    return {"policy_count": len(policies), "policies": policies}


def _write_csv(path: Path, policies: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "policy_id",
                "case_count",
                "completed_case_count",
                "failed_case_count",
                "mean_overall_score",
                "min_overall_score",
                "mean_placement_fit",
                "mean_seam_visibility",
                "mean_saliency_lift",
                "scenario_ids",
            ],
        )
        writer.writeheader()
        for item in policies:
            row = dict(item)
            row["scenario_ids"] = ",".join(item.get("scenario_ids", []))
            writer.writerow(row)


def main() -> int:
    args = _build_parser().parse_args()
    submitted_manifest = (
        _load_json(Path(args.submitted_manifest).resolve())
        if args.submitted_manifest
        else None
    )
    sweep_id = str(args.sweep_id or (submitted_manifest or {}).get("sweep_id", "")).strip()
    if not sweep_id:
        raise SystemExit("sweep id is required via --sweep-id or --submitted-manifest")
    artifacts_root = Path(args.artifacts_root).resolve()
    cases = _discover_cases(artifacts_root=artifacts_root, sweep_id=sweep_id)
    aggregate = _aggregate(cases)
    expected = _expected_cases(submitted_manifest)
    observed = {
        (
            str(case.get("policy_id", "")).strip(),
            str(case.get("scenario_id", "")).strip(),
        )
        for case in cases
    }
    output = {
        "sweep_id": sweep_id,
        "artifacts_root": str(artifacts_root),
        "expected_case_count": len(expected),
        "observed_case_count": len(observed),
        "missing_case_count": len(expected - observed),
        **aggregate,
    }
    json_path = (
        Path(args.output_json).resolve()
        if args.output_json
        else Path.cwd() / f"{sweep_id}.collected.json"
    )
    json_path.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    csv_path = (
        Path(args.output_csv).resolve()
        if args.output_csv
        else json_path.with_suffix(".csv")
    )
    _write_csv(csv_path, output["policies"])
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
