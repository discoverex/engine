#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import itertools
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

try:
    from infra.register import branch_deployments as _branch_deployments
    from infra.register import settings as _settings
except ImportError:  # pragma: no cover
    _branch_deployments = importlib.import_module("branch_deployments")
    _settings = importlib.import_module("settings")

experiment_deployment_name = _branch_deployments.experiment_deployment_name
SUPPORTED_DEPLOYMENT_PURPOSES = _branch_deployments.SUPPORTED_DEPLOYMENT_PURPOSES
SETTINGS = _settings.SETTINGS

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SPEC = SCRIPT_DIR / "job_specs" / "object_generation.standard.yaml"
DEFAULT_EXPERIMENT = "object-quality"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit an object-generation quality sweep to the generate Prefect flow."
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
    parser.add_argument("--retry-missing-limit", type=int, default=0)
    return parser


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must decode to an object")
    return payload


def _load_base_job_spec(path: Path) -> dict[str, Any]:
    payload = _load_yaml(path)
    if "inputs" not in payload:
        raise SystemExit(f"job spec at {path} must contain inputs")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must decode to an object")
    return payload


def _load_scenario(spec: dict[str, Any]) -> dict[str, str]:
    scenario = spec.get("scenario", {})
    if not isinstance(scenario, dict):
        raise SystemExit("scenario must be an object")
    scenario_id = str(scenario.get("scenario_id", "")).strip() or "transparent-three-object-quality"
    object_prompt = str(scenario.get("object_prompt", "")).strip()
    if not object_prompt:
        raise SystemExit("scenario.object_prompt is required")
    output = {"scenario_id": scenario_id}
    for key in (
        "object_base_prompt",
        "object_prompt",
        "object_base_negative_prompt",
        "object_negative_prompt",
        "object_prompt_style",
        "object_negative_profile",
        "object_count",
        "object_generation_size",
    ):
        value = scenario.get(key)
        if value not in (None, ""):
            output[key] = str(value)
    return output


def _parameter_grid(spec: dict[str, Any]) -> list[tuple[str, list[str]]]:
    parameters = spec.get("parameters", {})
    if not isinstance(parameters, dict) or not parameters:
        return []
    return [(str(key), [str(v) for v in values]) for key, values in parameters.items() if isinstance(values, list) and values]


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


def _fixed_overrides(spec: dict[str, Any]) -> list[str]:
    values = spec.get("fixed_overrides", [])
    if not isinstance(values, list):
        return []
    return [str(item) for item in values if str(item).strip()]


def build_sweep_manifest(spec_path: Path) -> dict[str, Any]:
    spec = _load_yaml(spec_path)
    base_job_spec = _load_base_job_spec(
        (spec_path.parent / str(spec.get("base_job_spec", DEFAULT_SPEC))).resolve()
        if spec.get("base_job_spec")
        else DEFAULT_SPEC
    )
    sweep_id = str(spec.get("sweep_id", "")).strip() or spec_path.stem
    search_stage = str(spec.get("search_stage", "coarse")).strip() or "coarse"
    experiment_name = (
        str(spec.get("experiment_name", "")).strip()
        or f"object-quality.{sweep_id}"
    )
    scenario = _load_scenario(spec)
    combos = _combination_records(_parameter_grid(spec))
    fixed_overrides = _fixed_overrides(spec)
    jobs: list[dict[str, Any]] = []
    for combo in combos:
        job_spec = deepcopy(base_job_spec)
        inputs = job_spec.setdefault("inputs", {})
        args = inputs.setdefault("args", {})
        overrides = list(inputs.get("overrides", []))
        args.update(scenario)
        args["sweep_id"] = sweep_id
        args["combo_id"] = combo["combo_id"]
        args["policy_id"] = combo["combo_id"]
        args["scenario_id"] = scenario["scenario_id"]
        args["search_stage"] = search_stage
        overrides.extend(fixed_overrides)
        for key, value in combo.items():
            if key == "combo_id":
                continue
            if key.startswith("inputs.args."):
                args[key.removeprefix("inputs.args.")] = value
                continue
            overrides.append(f"{key}={value}")
        overrides.append(f"adapters.tracker.experiment_name={experiment_name}")
        inputs["args"] = args
        inputs["overrides"] = _dedupe(overrides)
        job_spec["job_name"] = f"{sweep_id}--{combo['combo_id']}--{scenario['scenario_id']}"
        safe_experiment = experiment_name.replace("/", "-").strip() or "experiment"
        job_spec["outputs_prefix"] = f"exp/{safe_experiment}/{sweep_id}/{job_spec['job_name']}/"
        jobs.append(
            {
                "job_name": job_spec["job_name"],
                "combo_id": combo["combo_id"],
                "policy_id": combo["combo_id"],
                "scenario_id": scenario["scenario_id"],
                "job_spec": job_spec,
            }
        )
    return {
        "sweep_id": sweep_id,
        "search_stage": search_stage,
        "experiment_name": experiment_name,
        "combo_count": len(combos),
        "job_count": len(jobs),
        "jobs": jobs,
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _job_key(*, policy_id: str, scenario_id: str) -> str:
    return f"{policy_id}::{scenario_id}"


def _discover_collected_keys(*, artifacts_root: Path, sweep_id: str) -> set[str]:
    cases_dir = artifacts_root / "experiments" / "object_generation_sweeps" / sweep_id / "cases"
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
    )
    pending: list[dict[str, Any]] = []
    for job in manifest["jobs"]:
        key = _job_key(policy_id=str(job["policy_id"]), scenario_id=str(job["scenario_id"]))
        existing = existing_results.get(key)
        if existing is None:
            pending.append(job)
            continue
        submitted = bool(existing.get("submitted"))
        flow_run_id = str(existing.get("flow_run_id", "")).strip()
        if (not submitted) or (not flow_run_id):
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
        key = _job_key(
            policy_id=str(item.get("policy_id", "")),
            scenario_id=str(item.get("scenario_id", "")),
        )
        merged[key] = item
    results = sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("policy_id", "")),
            str(item.get("scenario_id", "")),
            str(item.get("job_name", "")),
        ),
    )
    return {
        "sweep_id": manifest["sweep_id"],
        "search_stage": manifest["search_stage"],
        "experiment_name": manifest["experiment_name"],
        "combo_count": manifest["combo_count"],
        "job_count": manifest["job_count"],
        "deployment": deployment,
        "results": results,
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
                    "submitted": False,
                    "deployment": resolved_deployment,
                    "work_queue_name": work_queue_name,
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
                "submitted": True,
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
        from infra.register.register_orchestrator_job import submit_job_spec
    except ImportError:  # pragma: no cover
        submit_job_spec = importlib.import_module("register_orchestrator_job").submit_job_spec
    return submit_job_spec


def main() -> int:
    args = _build_parser().parse_args()
    spec_path = Path(args.sweep_spec).resolve()
    manifest = build_sweep_manifest(spec_path)
    submitted_manifest = (
        _load_json(Path(args.submitted_manifest).resolve())
        if args.submitted_manifest
        else None
    )
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
    output_path = Path(args.output).resolve() if args.output else spec_path.with_suffix(".submitted.json")
    output_path.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
