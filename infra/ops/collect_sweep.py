#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from infra.ops.collect_object_generation_sweep import (
    _aggregate as _aggregate_object_generation,
    _classify_missing_case,
    _flow_run_states,
    _load_env_file,
    _recover_remote_cases,
    _write_csv as _write_object_csv,
    _write_html as _write_object_html,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and aggregate canonical sweep results."
    )
    parser.add_argument("--submitted-manifest", default=None)
    parser.add_argument("--sweep-id", default=None)
    parser.add_argument("--artifacts-root", default="/var/lib/discoverex/engine-runs")
    parser.add_argument(
        "--env-file",
        default=str(Path(__file__).resolve().parents[1] / "worker" / ".env.fixed"),
    )
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-csv", default=None)
    parser.add_argument("--output-html", default=None)
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must decode to an object")
    return payload


def _discover_cases(
    *,
    artifacts_root: Path,
    sweep_id: str,
    case_dir_name: str,
) -> list[dict[str, Any]]:
    root = artifacts_root / "experiments" / case_dir_name / sweep_id / "cases"
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


def _job_key(*, policy_id: str, scenario_id: str) -> str:
    return f"{policy_id}::{scenario_id}"


def _aggregate_combined_policies(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "cases": items,
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
    return policies


def _aggregate_combined(
    cases: list[dict[str, Any]],
    *,
    submitted_manifest: dict[str, Any] | None = None,
    flow_run_states: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    expected_results = list((submitted_manifest or {}).get("results", []))
    expected_by_key: dict[str, dict[str, Any]] = {}
    for item in expected_results:
        policy_id = str(item.get("policy_id", "")).strip()
        scenario_id = str(item.get("scenario_id", "")).strip()
        if policy_id and scenario_id:
            expected_by_key[_job_key(policy_id=policy_id, scenario_id=scenario_id)] = item
    observed_keys = {
        _job_key(
            policy_id=str(case.get("policy_id", "")).strip(),
            scenario_id=str(case.get("scenario_id", "")).strip(),
        )
        for case in cases
        if str(case.get("policy_id", "")).strip() and str(case.get("scenario_id", "")).strip()
    }
    missing_cases: list[dict[str, Any]] = []
    unsubmitted_cases: list[dict[str, Any]] = []
    failed_runs: list[dict[str, Any]] = []
    cancelled_runs: list[dict[str, Any]] = []
    pending_runs: list[dict[str, Any]] = []
    for key, item in sorted(expected_by_key.items()):
        if key in observed_keys:
            continue
        flow_run_id = str(item.get("flow_run_id", "")).strip()
        state = (flow_run_states or {}).get(flow_run_id) if flow_run_id else None
        record = _classify_missing_case(item, state)
        status = str(record.get("status", "")).strip()
        if status == "not_submitted":
            unsubmitted_cases.append(record)
        elif status == "pending":
            pending_runs.append(record)
        elif status == "failed":
            failed_runs.append(record)
        elif status == "cancelled":
            cancelled_runs.append(record)
        else:
            missing_cases.append(record)
    policies = _aggregate_combined_policies(cases)
    return {
        "policy_count": len(policies),
        "policies": policies,
        "missing_case_count": len(missing_cases),
        "missing_cases": missing_cases,
        "failed_run_count": len(failed_runs),
        "failed_runs": failed_runs,
        "cancelled_run_count": len(cancelled_runs),
        "cancelled_runs": cancelled_runs,
        "pending_run_count": len(pending_runs),
        "pending_runs": pending_runs,
        "not_submitted_count": len(unsubmitted_cases),
        "not_submitted_cases": unsubmitted_cases,
    }


def _aggregate(
    cases: list[dict[str, Any]],
    *,
    submitted_manifest: dict[str, Any] | None,
    flow_run_states: dict[str, dict[str, str]] | None,
    collector_adapter: str,
) -> dict[str, Any]:
    if collector_adapter == "combined":
        return _aggregate_combined(
            cases,
            submitted_manifest=submitted_manifest,
            flow_run_states=flow_run_states,
        )
    return _aggregate_object_generation(
        cases,
        submitted_manifest=submitted_manifest,
        flow_run_states=flow_run_states,
    )


def _write_combined_csv(path: Path, policies: list[dict[str, Any]]) -> None:
    import csv

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
            writer.writerow(
                {
                    "policy_id": item["policy_id"],
                    "case_count": item["case_count"],
                    "mean_composite_repr": item["mean_composite_repr"],
                    "min_composite_repr": item["min_composite_repr"],
                    "mean_verify_repr": item["mean_verify_repr"],
                    "mean_naturalness_repr": item["mean_naturalness_repr"],
                    "mean_object_repr": item["mean_object_repr"],
                    "min_object_verify_score": item["min_object_verify_score"],
                    "gallery_ref": item["gallery_ref"],
                }
            )


def main() -> int:
    args = _build_parser().parse_args()
    env_file = Path(str(args.env_file)).resolve() if args.env_file else None
    _load_env_file(env_file)
    submitted_manifest = (
        _load_json(Path(args.submitted_manifest).resolve())
        if args.submitted_manifest
        else None
    )
    sweep_id = str(args.sweep_id or (submitted_manifest or {}).get("sweep_id", "")).strip()
    if not sweep_id:
        raise SystemExit("sweep id is required via --sweep-id or --submitted-manifest")
    case_dir_name = str(
        (submitted_manifest or {}).get("case_dir_name", "object_generation_sweeps")
    ).strip() or "object_generation_sweeps"
    collector_adapter = str(
        (submitted_manifest or {}).get("collector_adapter", "object_generation")
    ).strip() or "object_generation"
    artifacts_root = Path(args.artifacts_root).resolve()
    cases = _discover_cases(
        artifacts_root=artifacts_root,
        sweep_id=sweep_id,
        case_dir_name=case_dir_name,
    )
    if submitted_manifest is not None:
        cases.extend(_recover_remote_cases(list(submitted_manifest.get("results", []))))
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for item in cases:
            key = (
                str(item.get("policy_id", "")).strip(),
                str(item.get("scenario_id", "")).strip(),
            )
            deduped[key] = item
        cases = list(deduped.values())
    expected_results = list((submitted_manifest or {}).get("results", []))
    states = _flow_run_states(expected_results) if expected_results else {}
    output = {
        "sweep_id": sweep_id,
        "artifacts_root": str(artifacts_root),
        "sweep_type": str((submitted_manifest or {}).get("sweep_type", "")).strip(),
        "collector_adapter": collector_adapter,
        **_aggregate(
            cases,
            submitted_manifest=submitted_manifest,
            flow_run_states=states,
            collector_adapter=collector_adapter,
        ),
    }
    json_path = (
        Path(args.output_json).resolve()
        if args.output_json
        else Path.cwd() / f"{sweep_id}.collected.json"
    )
    json_path.write_text(
        json.dumps(output, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    csv_path = (
        Path(args.output_csv).resolve()
        if args.output_csv
        else json_path.with_suffix(".csv")
    )
    if collector_adapter == "combined":
        _write_combined_csv(csv_path, output["policies"])
    else:
        _write_object_csv(csv_path, output["policies"])
    if args.output_html and collector_adapter != "combined":
        _write_object_html(Path(args.output_html).resolve(), output["policies"])
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
