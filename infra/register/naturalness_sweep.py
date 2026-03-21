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
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    pass

try:
    from infra.register import branch_deployments as _branch_deployments
    from infra.register import settings as _settings
except ImportError:  # pragma: no cover - direct script execution path
    _branch_deployments = importlib.import_module("branch_deployments")
    _settings = importlib.import_module("settings")

experiment_deployment_name = _branch_deployments.experiment_deployment_name
SETTINGS = _settings.SETTINGS

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SPEC = (
    SCRIPT_DIR
    / "job_specs"
    / "prod-gennat-pixart-layerdiffuse-hfregion-ldho1-8gb.yaml"
)
DEFAULT_EXPERIMENT = "naturalness"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit a naturalness parameter sweep to the generate Prefect flow."
    )
    parser.add_argument(
        "sweep_spec", help="YAML file defining scenarios and parameter grid"
    )
    parser.add_argument("--prefect-api-url", default=SETTINGS.prefect_api_url)
    parser.add_argument("--deployment", default=None)
    parser.add_argument("--branch", default=SETTINGS.register_flow_ref or "dev")
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default=None, help="Optional manifest output path")
    return parser


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"spec at {path} must decode to an object")
    return payload


def _load_base_job_spec(path: Path) -> dict[str, Any]:
    payload = _load_yaml(path)
    if "inputs" not in payload:
        raise SystemExit(f"job spec at {path} must contain inputs")
    return payload


def _load_scenarios(spec: dict[str, Any], sweep_path: Path) -> list[dict[str, str]]:
    csv_path = spec.get("scenarios_csv")
    if csv_path:
        resolved = (sweep_path.parent / str(csv_path)).resolve()
        rows = list(csv.DictReader(resolved.read_text(encoding="utf-8").splitlines()))
        return [_normalized_scenario(row, index + 1) for index, row in enumerate(rows)]
    scenarios = spec.get("scenarios", [])
    if not isinstance(scenarios, list) or not scenarios:
        raise SystemExit("sweep spec requires scenarios or scenarios_csv")
    return [
        _normalized_scenario(dict(item), index + 1)
        for index, item in enumerate(scenarios)
    ]


def _normalized_scenario(row: dict[str, Any], index: int) -> dict[str, str]:
    scenario_id = str(row.get("scenario_id", "")).strip() or f"scenario-{index:03d}"
    background_prompt = str(row.get("background_prompt", "")).strip()
    object_prompt = str(row.get("object_prompt", "")).strip()
    if not background_prompt or not object_prompt:
        raise SystemExit(
            f"scenario {scenario_id} requires background_prompt and object_prompt"
        )
    output = {
        "scenario_id": scenario_id,
        "background_prompt": background_prompt,
        "object_prompt": object_prompt,
    }
    for key in (
        "background_negative_prompt",
        "object_negative_prompt",
        "final_prompt",
        "final_negative_prompt",
    ):
        value = str(row.get(key, "")).strip()
        if value:
            output[key] = value
    scenario_overrides = str(row.get("scenario_overrides", "")).strip()
    if scenario_overrides:
        output["scenario_overrides"] = scenario_overrides
    return output


def _parameter_grid(spec: dict[str, Any]) -> list[tuple[str, list[str]]]:
    parameters = spec.get("parameters", {})
    if parameters in (None, {}):
        return []
    if not isinstance(parameters, dict):
        raise SystemExit("parameters must be a mapping when provided")
    grid: list[tuple[str, list[str]]] = []
    for name, values in parameters.items():
        if not isinstance(values, list) or not values:
            raise SystemExit(f"parameter {name} must map to a non-empty list")
        grid.append((str(name), [str(value) for value in values]))
    return grid


def _combination_records(grid: list[tuple[str, list[str]]]) -> list[dict[str, str]]:
    if not grid:
        return [{"combo_id": "combo-001"}]
    keys = [name for name, _ in grid]
    value_lists = [values for _, values in grid]
    records: list[dict[str, str]] = []
    for index, values in enumerate(itertools.product(*value_lists), start=1):
        combo = {key: value for key, value in zip(keys, values, strict=True)}
        combo["combo_id"] = f"combo-{index:03d}"
        records.append(combo)
    return records


def _fixed_overrides(spec: dict[str, Any]) -> list[str]:
    values = spec.get("fixed_overrides", [])
    if not isinstance(values, list):
        raise SystemExit("fixed_overrides must be a list")
    return [str(item) for item in values]


def _variant_specs(spec: dict[str, Any]) -> list[dict[str, Any]]:
    raw = spec.get("variants", [])
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
                "overrides": [str(value) for value in overrides if str(value).strip()],
            }
        )
    return variants


def _job_spec_for_case(
    *,
    base_job_spec: dict[str, Any],
    scenario: dict[str, str],
    combo: dict[str, str],
    sweep_id: str,
    search_stage: str,
    experiment_name: str,
    fixed_overrides: list[str],
    variant_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    job_spec = deepcopy(base_job_spec)
    inputs = job_spec.setdefault("inputs", {})
    args = inputs.setdefault("args", {})
    overrides = list(inputs.get("overrides", []))
    overrides.extend(fixed_overrides)
    scenario_overrides = str(scenario.get("scenario_overrides", "")).strip()
    if scenario_overrides:
        overrides.extend(
            item.strip() for item in scenario_overrides.split("||") if item.strip()
        )
    overrides.extend(
        f"{key}={value}" for key, value in combo.items() if key != "combo_id"
    )
    overrides.append(f"adapters.tracker.experiment_name={experiment_name}")
    args.update(scenario)
    args["sweep_id"] = sweep_id
    args["combo_id"] = combo["combo_id"]
    args["scenario_id"] = scenario["scenario_id"]
    args["search_stage"] = search_stage
    if variant_specs:
        args["variant_specs_json"] = json.dumps(variant_specs, ensure_ascii=True)
        args["variant_count"] = len(variant_specs)
    inputs["args"] = args
    if variant_specs:
        overrides.append("flows/generate=inpaint_variant_pack")
    inputs["overrides"] = _dedupe(overrides)
    job_spec["job_name"] = (
        f"{sweep_id}--{search_stage}--{combo['combo_id']}--{scenario['scenario_id']}"
    )
    safe_experiment = experiment_name.replace("/", "-").strip() or "experiment"
    job_spec["outputs_prefix"] = (
        f"exp/{safe_experiment}/{sweep_id}/{job_spec['job_name']}/"
    )
    return job_spec


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


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
        or f"discoverex-naturalness-search-{sweep_id}"
    )
    scenarios = _load_scenarios(spec, spec_path)
    combos = _combination_records(_parameter_grid(spec))
    fixed_overrides = _fixed_overrides(spec)
    variant_specs = _variant_specs(spec)
    jobs: list[dict[str, Any]] = []
    for combo in combos:
        for scenario in scenarios:
            job_spec = _job_spec_for_case(
                base_job_spec=base_job_spec,
                scenario=scenario,
                combo=combo,
                sweep_id=sweep_id,
                search_stage=search_stage,
                experiment_name=experiment_name,
                fixed_overrides=fixed_overrides,
                variant_specs=variant_specs,
            )
            jobs.append(
                {
                    "job_name": job_spec["job_name"],
                    "combo_id": combo["combo_id"],
                    "scenario_id": scenario["scenario_id"],
                    "variant_count": len(variant_specs),
                    "overrides": job_spec["inputs"]["overrides"],
                    "job_spec": job_spec,
                }
            )
    return {
        "sweep_id": sweep_id,
        "search_stage": search_stage,
        "experiment_name": experiment_name,
        "combo_count": len(combos),
        "scenario_count": len(scenarios),
        "variant_count": len(variant_specs),
        "job_count": len(jobs),
        "jobs": jobs,
    }


def submit_manifest(
    manifest: dict[str, Any],
    *,
    prefect_api_url: str,
    branch: str,
    experiment: str,
    deployment: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    submit_job_spec = _load_submit_job_spec()
    resolved_deployment = deployment or experiment_deployment_name(
        branch,
        experiment=experiment,
    )
    results: list[dict[str, Any]] = []
    for item in manifest["jobs"]:
        job_spec = item["job_spec"]
        if dry_run:
            results.append(
                {
                    "job_name": item["job_name"],
                    "combo_id": item["combo_id"],
                    "scenario_id": item["scenario_id"],
                    "submitted": False,
                    "deployment": resolved_deployment,
                }
            )
            continue
        output = submit_job_spec(
            job_spec=job_spec,
            prefect_api_url=prefect_api_url,
            deployment=resolved_deployment,
            job_name=item["job_name"],
        )
        results.append(
            {
                "job_name": item["job_name"],
                "combo_id": item["combo_id"],
                "scenario_id": item["scenario_id"],
                "submitted": True,
                "flow_run_id": output.get("flow_run_id"),
                "deployment": resolved_deployment,
            }
        )
    return {
        "sweep_id": manifest["sweep_id"],
        "search_stage": manifest["search_stage"],
        "experiment_name": manifest["experiment_name"],
        "combo_count": manifest["combo_count"],
        "scenario_count": manifest["scenario_count"],
        "variant_count": manifest.get("variant_count", 0),
        "job_count": manifest["job_count"],
        "deployment": resolved_deployment,
        "results": results,
    }


def _load_submit_job_spec() -> Callable[..., dict[str, Any]]:
    try:
        from infra.register.register_orchestrator_job import submit_job_spec
    except ImportError:  # pragma: no cover - direct script execution path
        submit_job_spec = importlib.import_module(
            "register_orchestrator_job"
        ).submit_job_spec
    return submit_job_spec


def main() -> int:
    args = _build_parser().parse_args()
    spec_path = Path(args.sweep_spec).resolve()
    manifest = build_sweep_manifest(spec_path)
    output = submit_manifest(
        manifest,
        prefect_api_url=args.prefect_api_url,
        branch=args.branch,
        experiment=args.experiment,
        deployment=args.deployment,
        dry_run=bool(args.dry_run),
    )
    output_path = (
        Path(args.output).resolve()
        if args.output
        else spec_path.with_suffix(".submitted.json")
    )
    output_path.write_text(
        json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
