#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and aggregate combined fine-to-inpaint sweep results."
    )
    parser.add_argument("--submitted-manifest", default=None)
    parser.add_argument("--sweep-id", default=None)
    parser.add_argument("--artifacts-root", default="/var/lib/discoverex/engine-runs")
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


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        policy_id = str(case.get("policy_id", "")).strip() or "unknown"
        grouped.setdefault(policy_id, []).append(case)
    policies: list[dict[str, Any]] = []
    for policy_id, items in sorted(grouped.items()):
        composite_scores = [
            float(scores.get("composite_repr"))
            for case in items
            if isinstance((scores := case.get("representative_scores")), dict)
            and isinstance(scores.get("composite_repr"), (int, float))
        ]
        verify_scores = [
            float(scores.get("verify_repr"))
            for case in items
            if isinstance((scores := case.get("representative_scores")), dict)
            and isinstance(scores.get("verify_repr"), (int, float))
        ]
        naturalness_scores = [
            float(scores.get("naturalness_repr"))
            for case in items
            if isinstance((scores := case.get("representative_scores")), dict)
            and isinstance(scores.get("naturalness_repr"), (int, float))
        ]
        object_scores = [
            float(scores.get("object_repr"))
            for case in items
            if isinstance((scores := case.get("representative_scores")), dict)
            and isinstance(scores.get("object_repr"), (int, float))
        ]
        object_verify_floor = [
            min(
                float(obj.get("verify_score", 0.0) or 0.0)
                for obj in case.get("object_scores", [])
                if isinstance(obj, dict)
            )
            for case in items
            if isinstance(case.get("object_scores"), list) and case.get("object_scores")
        ]
        policies.append(
            {
                "policy_id": policy_id,
                "case_count": len(items),
                "mean_composite_repr": _mean(composite_scores),
                "min_composite_repr": round(min(composite_scores), 4)
                if composite_scores
                else 0.0,
                "mean_verify_repr": _mean(verify_scores),
                "mean_naturalness_repr": _mean(naturalness_scores),
                "mean_object_repr": _mean(object_scores),
                "min_object_verify_score": round(min(object_verify_floor), 4)
                if object_verify_floor
                else 0.0,
                "gallery_ref": str(items[0].get("quality_gallery_ref", "")).strip()
                if items
                else "",
            }
        )
    policies.sort(
        key=lambda item: (
            -float(item["mean_composite_repr"]),
            -float(item["mean_verify_repr"]),
            -float(item["mean_naturalness_repr"]),
            -float(item["mean_object_repr"]),
            -float(item["min_object_verify_score"]),
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
                "mean_composite_repr",
                "min_composite_repr",
                "mean_verify_repr",
                "mean_naturalness_repr",
                "mean_object_repr",
                "min_object_verify_score",
                "gallery_ref",
            ],
        )
        writer.writeheader()
        for item in policies:
            writer.writerow(item)


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
    output = {
        "sweep_id": sweep_id,
        "artifacts_root": str(artifacts_root),
        **_aggregate(cases),
    }
    json_path = (
        Path(args.output_json).resolve()
        if args.output_json
        else Path.cwd() / f"{sweep_id}.combined.collected.json"
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
