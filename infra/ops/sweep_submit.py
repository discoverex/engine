#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib
import itertools
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

try:
    from infra.ops import branch_deployments as _branch_deployments
    from infra.ops import settings as _settings
except ImportError:  # pragma: no cover
    _branch_deployments = importlib.import_module("branch_deployments")
    _settings = importlib.import_module("settings")

experiment_deployment_name = _branch_deployments.experiment_deployment_name
SUPPORTED_DEPLOYMENT_PURPOSES = _branch_deployments.SUPPORTED_DEPLOYMENT_PURPOSES
SETTINGS = _settings.SETTINGS

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EXPERIMENT = "object-quality"
DEFAULT_OBJECT_BASE_SPEC = SCRIPT_DIR / "specs" / "job" / "object_generation.standard.yaml"
DEFAULT_COMBINED_BASE_SPEC = SCRIPT_DIR / "specs" / "job" / "generate_verify.standard.yaml"
STANDARD_SPEC_VERSION = "v1"
STANDARD_MANIFEST_VERSION = "v1"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit a sweep from a standard or legacy sweep spec."
    )
    parser.add_argument("sweep_spec")
    parser.add_argument("--prefect-api-url", default=SETTINGS.prefect_api_url)
    parser.add_argument("--deployment", default=None)
    parser.add_argument(
        "--purpose",
        choices=SUPPORTED_DEPLOYMENT_PURPOSES,
        default="batch",
    )
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument("--work-queue-name", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--submitted-manifest", default=None)
    parser.add_argument("--artifacts-root", default="/var/lib/discoverex/engine-runs")
    parser.add_argument("--retry-missing-limit", "--limit", dest="retry_missing_limit", type=int, default=0)
    return parser


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must decode to an object")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must decode to an object")
    return payload


def _default_submitted_manifest_path(*, sweep_id: str) -> Path:
    return SCRIPT_DIR / "manifests" / f"{sweep_id}.submitted.json"


def _load_base_job_spec(path: Path) -> dict[str, Any]:
    payload = _load_yaml(path)
    if "inputs" not in payload:
        raise SystemExit(f"job spec at {path} must contain inputs")
    return payload


def _resolve_base_job_spec(spec_path: Path, raw_value: str) -> Path:
    raw_path = Path(raw_value)
    resolved = (
        raw_path.resolve()
        if raw_path.is_absolute()
        else (spec_path.parent / raw_value).resolve()
    )
    if resolved.exists():
        return resolved
    legacy_text = raw_value.replace("/job_specs/", "/job/").replace("job_specs/", "job/")
    if legacy_text != raw_value:
        legacy_resolved = (
            Path(legacy_text).resolve()
            if Path(legacy_text).is_absolute()
            else (spec_path.parent / legacy_text).resolve()
        )
        if legacy_resolved.exists():
            return legacy_resolved
    return resolved


def _normalized_scenario_from_mapping(row: dict[str, Any], index: int) -> dict[str, Any]:
    scenario_id = str(row.get("scenario_id", "")).strip() or f"scenario-{index:03d}"
    output: dict[str, Any] = {"scenario_id": scenario_id}
    for key, value in row.items():
        if key == "scenario_id" or value in (None, ""):
            continue
        output[str(key)] = value
    return output


def _load_scenarios_from_csv(path: Path) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    return [_normalized_scenario_from_mapping(dict(row), index + 1) for index, row in enumerate(rows)]


def _normalize_parameters(raw: Any) -> list[dict[str, Any]]:
    if raw in (None, {}):
        return []
    if not isinstance(raw, dict):
        raise SystemExit("parameters must be a mapping when provided")
    output: list[dict[str, Any]] = []
    for name, values in raw.items():
        if not isinstance(values, list) or not values:
            raise SystemExit(f"parameter {name} must map to a non-empty list")
        output.append({"name": str(name), "values": [str(value) for value in values]})
    return output


def _normalize_variants(raw: Any) -> list[dict[str, Any]]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise SystemExit("variants must be a list")
    variants: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SystemExit("each variant must be an object")
        variant_id = str(item.get("variant_id", "")).strip() or f"variant-{index:02d}"
        overrides = item.get("overrides", [])
        if not isinstance(overrides, list):
            raise SystemExit(f"variant {variant_id} overrides must be a list")
        variants.append(
            {
                "variant_id": variant_id,
                "label": str(item.get("label", "")).strip() or variant_id,
                "overrides": [str(value) for value in overrides if str(value).strip()],
            }
        )
    return variants


def _normalize_fixed_overrides(raw: Any) -> list[str]:
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise SystemExit("fixed_overrides must be a list")
    return [str(item) for item in raw if str(item).strip()]


def _normalize_standard_spec(spec: dict[str, Any], *, spec_path: Path) -> dict[str, Any]:
    scenarios_raw = spec.get("scenarios")
    if scenarios_raw in (None, []):
        raise SystemExit("standard sweep spec requires scenarios")
    if not isinstance(scenarios_raw, list):
        raise SystemExit("scenarios must be a list")
    execution = spec.get("execution", {})
    if execution in (None, {}):
        execution = {}
    if not isinstance(execution, dict):
        raise SystemExit("execution must be an object when provided")
    runner_type = str(execution.get("runner_type", "")).strip() or "object_generation"
    collector_adapter = str(execution.get("collector_adapter", "")).strip() or (
        "combined" if runner_type == "combined" else "object_generation"
    )
    artifact_namespace = str(execution.get("artifact_namespace", "")).strip() or (
        "naturalness_sweeps" if collector_adapter == "combined" else "object_generation_sweeps"
    )
    mode = str(execution.get("mode", "")).strip() or (
        "variant_pack" if spec.get("variants") else "case_per_run"
    )
    base_job_spec_raw = str(spec.get("base_job_spec", "")).strip()
    if not base_job_spec_raw:
        base_job_spec_raw = (
            str(DEFAULT_COMBINED_BASE_SPEC)
            if runner_type == "combined"
            else str(DEFAULT_OBJECT_BASE_SPEC)
        )
    base_job_spec = _resolve_base_job_spec(spec_path, base_job_spec_raw)
    return {
        "schema_version": str(spec.get("schema_version", "")).strip() or STANDARD_SPEC_VERSION,
        "sweep_id": str(spec.get("sweep_id", "")).strip() or spec_path.stem,
        "search_stage": str(spec.get("search_stage", "")).strip() or "coarse",
        "experiment_name": str(spec.get("experiment_name", "")).strip() or f"sweep.{spec_path.stem}",
        "base_job_spec": str(base_job_spec),
        "fixed_overrides": _normalize_fixed_overrides(spec.get("fixed_overrides")),
        "scenarios": [
            _normalized_scenario_from_mapping(dict(item), index + 1)
            for index, item in enumerate(scenarios_raw)
            if isinstance(item, dict)
        ],
        "parameters": _normalize_parameters(spec.get("parameters")),
        "variants": _normalize_variants(spec.get("variants")),
        "execution": {
            "mode": mode,
            "runner_type": runner_type,
            "collector_adapter": collector_adapter,
            "artifact_namespace": artifact_namespace,
        },
    }


def _normalize_legacy_spec(spec: dict[str, Any], *, spec_path: Path) -> dict[str, Any]:
    if str(spec.get("schema_version", "")).strip() == STANDARD_SPEC_VERSION:
        return _normalize_standard_spec(spec, spec_path=spec_path)
    scenario = spec.get("scenario")
    if isinstance(scenario, dict) and scenario:
        standard = {
            "schema_version": STANDARD_SPEC_VERSION,
            "sweep_id": spec.get("sweep_id"),
            "search_stage": spec.get("search_stage"),
            "experiment_name": spec.get("experiment_name"),
            "base_job_spec": spec.get("base_job_spec") or str(DEFAULT_OBJECT_BASE_SPEC),
            "fixed_overrides": spec.get("fixed_overrides") or [],
            "scenarios": [scenario],
            "parameters": spec.get("parameters") or {},
            "variants": [],
            "execution": {
                "mode": "case_per_run",
                "runner_type": "object_generation",
                "collector_adapter": "object_generation",
                "artifact_namespace": "object_generation_sweeps",
            },
        }
        return _normalize_standard_spec(standard, spec_path=spec_path)
    scenarios_csv = spec.get("scenarios_csv")
    if scenarios_csv:
        csv_path = (spec_path.parent / str(scenarios_csv)).resolve()
        scenarios = _load_scenarios_from_csv(csv_path)
    else:
        scenarios_raw = spec.get("scenarios", [])
        if not isinstance(scenarios_raw, list) or not scenarios_raw:
            raise SystemExit("legacy sweep spec requires scenario or scenarios/scenarios_csv")
        scenarios = [
            _normalized_scenario_from_mapping(dict(item), index + 1)
            for index, item in enumerate(scenarios_raw)
            if isinstance(item, dict)
        ]
    mode = str(spec.get("execution_mode", "")).strip() or (
        "variant_pack" if spec.get("variants") else "case_per_run"
    )
    standard = {
        "schema_version": STANDARD_SPEC_VERSION,
        "sweep_id": spec.get("sweep_id"),
        "search_stage": spec.get("search_stage"),
        "experiment_name": spec.get("experiment_name"),
        "base_job_spec": spec.get("base_job_spec") or str(DEFAULT_COMBINED_BASE_SPEC),
        "fixed_overrides": spec.get("fixed_overrides") or [],
        "scenarios": scenarios,
        "parameters": spec.get("parameters") or {},
        "variants": spec.get("variants") or [],
        "execution": {
            "mode": mode,
            "runner_type": "combined",
            "collector_adapter": "combined",
            "artifact_namespace": "naturalness_sweeps",
        },
    }
    return _normalize_standard_spec(standard, spec_path=spec_path)


def _parameter_grid(parameters: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    return [(str(item["name"]), [str(value) for value in item["values"]]) for item in parameters]


def _combination_records(grid: list[tuple[str, list[str]]]) -> list[dict[str, str]]:
    if not grid:
        return [{"combo_id": "combo-001"}]
    keys = [name for name, _ in grid]
    value_lists = [values for _, values in grid]
    combos: list[dict[str, str]] = []
    for index, values in enumerate(itertools.product(*value_lists), start=1):
        combo = {key: value for key, value in zip(keys, values, strict=True)}
        combo["combo_id"] = f"combo-{index:03d}"
        combos.append(combo)
    return combos


def _policy_records(
    *,
    combos: list[dict[str, str]],
    variants: list[dict[str, Any]],
    mode: str,
) -> list[dict[str, Any]]:
    if not variants:
        return [
            {
                "policy_id": combo["combo_id"],
                "combo": combo,
                "variant_id": "",
                "variant_overrides": [],
                "variant_specs": [],
            }
            for combo in combos
        ]
    if mode == "variant_pack":
        return [
            {
                "policy_id": combo["combo_id"],
                "combo": combo,
                "variant_id": "",
                "variant_overrides": [],
                "variant_specs": variants,
            }
            for combo in combos
        ]
    records: list[dict[str, Any]] = []
    for combo in combos:
        for variant in variants:
            policy_id = str(variant["variant_id"]).strip() or combo["combo_id"]
            if combo["combo_id"] != "combo-001":
                policy_id = f"{combo['combo_id']}--{policy_id}"
            records.append(
                {
                    "policy_id": policy_id,
                    "combo": combo,
                    "variant_id": str(variant["variant_id"]),
                    "variant_overrides": list(variant["overrides"]),
                    "variant_specs": [],
                }
            )
    return records


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _job_spec_for_case(
    *,
    base_job_spec: dict[str, Any],
    scenario: dict[str, Any],
    combo: dict[str, str],
    policy: dict[str, Any],
    sweep_id: str,
    search_stage: str,
    experiment_name: str,
    fixed_overrides: list[str],
    execution: dict[str, str],
) -> dict[str, Any]:
    job_spec = deepcopy(base_job_spec)
    inputs = job_spec.setdefault("inputs", {})
    args = inputs.setdefault("args", {})
    overrides = list(inputs.get("overrides", []))
    overrides.extend(fixed_overrides)
    scenario_overrides = str(scenario.get("scenario_overrides", "")).strip()
    if scenario_overrides:
        overrides.extend(item.strip() for item in scenario_overrides.split("||") if item.strip())
    runner_type = str(execution["runner_type"])
    if runner_type == "object_generation":
        args.update({key: str(value) for key, value in scenario.items() if value not in (None, "")})
        for key, value in combo.items():
            if key == "combo_id":
                continue
            if key.startswith("inputs.args."):
                args[key.removeprefix("inputs.args.")] = value
            else:
                overrides.append(f"{key}={value}")
    else:
        if str(scenario.get("background_asset_ref", "")).strip():
            args["background_prompt"] = ""
            args["background_negative_prompt"] = ""
        args.update({key: value for key, value in scenario.items() if value not in (None, "")})
        for key, value in combo.items():
            if key == "combo_id":
                continue
            overrides.append(f"{key}={value}")
        overrides.extend(policy["variant_overrides"])
        if execution["mode"] == "variant_pack" and policy["variant_specs"]:
            args["variant_specs_json"] = json.dumps(policy["variant_specs"], ensure_ascii=True)
            args["variant_count"] = len(policy["variant_specs"])
            overrides.append("flows/generate=inpaint_variant_pack")
    args["sweep_id"] = sweep_id
    args["combo_id"] = combo["combo_id"]
    args["policy_id"] = policy["policy_id"]
    args["scenario_id"] = str(scenario["scenario_id"])
    args["search_stage"] = search_stage
    args["sweep_runner_type"] = str(execution["runner_type"])
    args["sweep_collector_adapter"] = str(execution["collector_adapter"])
    args["sweep_artifact_namespace"] = str(execution["artifact_namespace"])
    args["sweep_execution_mode"] = str(execution["mode"])
    if policy["variant_id"]:
        args["variant_id"] = policy["variant_id"]
    overrides.append(f"adapters.tracker.experiment_name={experiment_name}")
    inputs["args"] = args
    inputs["overrides"] = _dedupe(overrides)
    job_spec["job_name"] = f"{sweep_id}--{policy['policy_id']}--{scenario['scenario_id']}"
    safe_experiment = experiment_name.replace("/", "-").strip() or "experiment"
    job_spec["outputs_prefix"] = f"exp/{safe_experiment}/{sweep_id}/{job_spec['job_name']}/"
    return job_spec


def build_standard_spec(spec_path: Path) -> dict[str, Any]:
    raw = _load_yaml(spec_path)
    return _normalize_legacy_spec(raw, spec_path=spec_path)


def build_sweep_manifest(spec_path: Path) -> dict[str, Any]:
    standard_spec = build_standard_spec(spec_path)
    base_job_spec = _load_base_job_spec(Path(str(standard_spec["base_job_spec"])).resolve())
    combos = _combination_records(_parameter_grid(list(standard_spec["parameters"])))
    execution = dict(standard_spec["execution"])
    policies = _policy_records(
        combos=combos,
        variants=list(standard_spec["variants"]),
        mode=str(execution["mode"]),
    )
    jobs: list[dict[str, Any]] = []
    for policy in policies:
        for scenario in standard_spec["scenarios"]:
            job_spec = _job_spec_for_case(
                base_job_spec=base_job_spec,
                scenario=scenario,
                combo=policy["combo"],
                policy=policy,
                sweep_id=str(standard_spec["sweep_id"]),
                search_stage=str(standard_spec["search_stage"]),
                experiment_name=str(standard_spec["experiment_name"]),
                fixed_overrides=list(standard_spec["fixed_overrides"]),
                execution=execution,
            )
            jobs.append(
                {
                    "job_name": job_spec["job_name"],
                    "combo_id": policy["combo"]["combo_id"],
                    "policy_id": policy["policy_id"],
                    "scenario_id": str(scenario["scenario_id"]),
                    "variant_id": str(policy["variant_id"]),
                    "variant_count": len(policy["variant_specs"]) if policy["variant_specs"] else (1 if policy["variant_id"] else 0),
                    "job_spec": job_spec,
                }
            )
    return {
        "manifest_version": STANDARD_MANIFEST_VERSION,
        "spec_version": str(standard_spec["schema_version"]),
        "standard_spec": standard_spec,
        "sweep_id": str(standard_spec["sweep_id"]),
        "search_stage": str(standard_spec["search_stage"]),
        "experiment_name": str(standard_spec["experiment_name"]),
        "execution": execution,
        "combo_count": len(combos),
        "scenario_count": len(standard_spec["scenarios"]),
        "variant_count": len(standard_spec["variants"]),
        "policy_count": len(policies),
        "job_count": len(jobs),
        "jobs": jobs,
        "sweep_type": str(execution["runner_type"]),
        "canonical_version": STANDARD_MANIFEST_VERSION,
        "collector_adapter": str(execution["collector_adapter"]),
        "case_dir_name": str(execution["artifact_namespace"]),
        "case_artifact_logical_name": "quality_case_json",
    }


def _job_key(*, policy_id: str, scenario_id: str) -> str:
    return f"{policy_id}::{scenario_id}"


def _discover_collected_keys(*, artifacts_root: Path, sweep_id: str, case_dir_name: str) -> set[str]:
    cases_dir = artifacts_root / "experiments" / case_dir_name / sweep_id / "cases"
    if not cases_dir.exists():
        return set()
    collected: set[str] = set()
    for path in sorted(cases_dir.glob("*.json")):
        payload = _load_json(path)
        policy_id = str(payload.get("policy_id", "")).strip()
        scenario_id = str(payload.get("scenario_id", "")).strip()
        if policy_id and scenario_id:
            collected.add(_job_key(policy_id=policy_id, scenario_id=scenario_id))
    return collected


def _result_map(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for item in results:
        policy_id = str(item.get("policy_id", "")).strip()
        scenario_id = str(item.get("scenario_id", "")).strip()
        if not policy_id or not scenario_id:
            continue
        mapped[_job_key(policy_id=policy_id, scenario_id=scenario_id)] = item
    return mapped


def _filter_jobs_for_retry(
    *,
    manifest: dict[str, Any],
    submitted_manifest: dict[str, Any] | None,
    artifacts_root: Path,
    retry_missing_limit: int,
) -> list[dict[str, Any]]:
    existing_results = _result_map(list((submitted_manifest or {}).get("results", [])))
    collected_keys = _discover_collected_keys(
        artifacts_root=artifacts_root,
        sweep_id=str(manifest["sweep_id"]),
        case_dir_name=str(manifest["case_dir_name"]),
    )
    pending: list[dict[str, Any]] = []
    for job in manifest["jobs"]:
        key = _job_key(policy_id=str(job["policy_id"]), scenario_id=str(job["scenario_id"]))
        existing = existing_results.get(key)
        if existing is None:
            pending.append(job)
            continue
        if (not bool(existing.get("submitted"))) or (not str(existing.get("flow_run_id", "")).strip()):
            pending.append(job)
            continue
        if key not in collected_keys:
            pending.append(job)
    if retry_missing_limit > 0:
        return pending[:retry_missing_limit]
    return pending


def _merge_results(
    *,
    submitted_manifest: dict[str, Any] | None,
    new_results: list[dict[str, Any]],
    manifest: dict[str, Any],
    deployment: str,
) -> dict[str, Any]:
    existing = list((submitted_manifest or {}).get("results", []))
    merged = _result_map(existing)
    for item in new_results:
        key = _job_key(policy_id=str(item.get("policy_id", "")), scenario_id=str(item.get("scenario_id", "")))
        updated = dict(merged.get(key, {}))
        updated.update(item)
        merged[key] = updated
    return {
        "manifest_version": manifest["manifest_version"],
        "spec_version": manifest["spec_version"],
        "sweep_id": manifest["sweep_id"],
        "search_stage": manifest["search_stage"],
        "experiment_name": manifest["experiment_name"],
        "execution": dict(manifest["execution"]),
        "sweep_type": manifest["sweep_type"],
        "canonical_version": manifest["canonical_version"],
        "collector_adapter": manifest["collector_adapter"],
        "case_dir_name": manifest["case_dir_name"],
        "case_artifact_logical_name": manifest["case_artifact_logical_name"],
        "combo_count": manifest["combo_count"],
        "scenario_count": manifest["scenario_count"],
        "variant_count": manifest["variant_count"],
        "policy_count": manifest["policy_count"],
        "job_count": manifest["job_count"],
        "deployment": deployment,
        "results": list(merged.values()),
    }


def submit_manifest(
    manifest: dict[str, Any],
    *,
    prefect_api_url: str,
    purpose: str,
    experiment: str,
    deployment: str | None,
    work_queue_name: str | None,
    dry_run: bool,
    submitted_manifest: dict[str, Any] | None = None,
    artifacts_root: Path | None = None,
    retry_missing_limit: int = 0,
) -> dict[str, Any]:
    submit_job_spec = _load_submit_job_spec()
    resolved_deployment = deployment or experiment_deployment_name(purpose, experiment=experiment)
    jobs = list(manifest["jobs"])
    if submitted_manifest is not None or retry_missing_limit > 0:
        jobs = _filter_jobs_for_retry(
            manifest=manifest,
            submitted_manifest=submitted_manifest,
            artifacts_root=artifacts_root or Path("/var/lib/discoverex/engine-runs"),
            retry_missing_limit=retry_missing_limit,
        )
    results: list[dict[str, Any]] = []
    for item in jobs:
        if dry_run:
            results.append(
                {
                    "job_name": item["job_name"],
                    "combo_id": item["combo_id"],
                    "policy_id": item["policy_id"],
                    "scenario_id": item["scenario_id"],
                    "variant_id": item.get("variant_id", ""),
                    "submitted": False,
                    "status": "not_submitted",
                    "deployment": resolved_deployment,
                    "work_queue_name": work_queue_name,
                    "outputs_prefix": item["job_spec"].get("outputs_prefix"),
                }
            )
            continue
        output = submit_job_spec(
            job_spec=item["job_spec"],
            prefect_api_url=prefect_api_url,
            deployment=resolved_deployment,
            job_name=item["job_name"],
            work_queue_name=work_queue_name,
        )
        results.append(
            {
                "job_name": item["job_name"],
                "combo_id": item["combo_id"],
                "policy_id": item["policy_id"],
                "scenario_id": item["scenario_id"],
                "variant_id": item.get("variant_id", ""),
                "submitted": True,
                "status": "pending",
                "flow_run_id": output.get("flow_run_id"),
                "deployment": resolved_deployment,
                "work_queue_name": work_queue_name,
                "outputs_prefix": item["job_spec"].get("outputs_prefix"),
            }
        )
    return _merge_results(
        submitted_manifest=submitted_manifest,
        new_results=results,
        manifest=manifest,
        deployment=resolved_deployment,
    )


def _load_submit_job_spec() -> Callable[..., dict[str, Any]]:
    try:
        from infra.ops.register_orchestrator_job import submit_job_spec
    except ImportError:  # pragma: no cover
        submit_job_spec = importlib.import_module("register_orchestrator_job").submit_job_spec
    return submit_job_spec


def main() -> int:
    args = _build_parser().parse_args()
    spec_path = Path(args.sweep_spec).resolve()
    manifest = build_sweep_manifest(spec_path)
    default_output_path = _default_submitted_manifest_path(sweep_id=str(manifest["sweep_id"]))
    submitted_manifest = _load_json(Path(args.submitted_manifest).resolve()) if args.submitted_manifest else None
    output = submit_manifest(
        manifest,
        prefect_api_url=args.prefect_api_url,
        purpose=args.purpose,
        experiment=args.experiment,
        deployment=args.deployment,
        work_queue_name=args.work_queue_name,
        dry_run=bool(args.dry_run),
        submitted_manifest=submitted_manifest,
        artifacts_root=Path(args.artifacts_root).resolve(),
        retry_missing_limit=max(0, int(args.retry_missing_limit)),
    )
    output_path = Path(args.output).resolve() if args.output else default_output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
