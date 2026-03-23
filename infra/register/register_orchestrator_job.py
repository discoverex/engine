#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import yaml
from prefect.client.orchestration import SyncPrefectClient, get_client
from prefect.client.schemas.filters import DeploymentFilter, DeploymentFilterName
from prefect.settings import PREFECT_API_URL, temporary_settings

if TYPE_CHECKING:
    from infra.register.job_types import JobSpec, JobSpecInputs
else:
    JobSpec = dict[str, Any]
    JobSpecInputs = dict[str, Any]

from infra.register.branch_deployments import (
    DEFAULT_FLOW_KIND,
    deployment_name_for_purpose,
    flow_entrypoint_for_kind,
)
from infra.register.settings import SETTINGS

V1_COMMANDS = ("gen-verify", "verify-only", "replay-eval")
V2_COMMANDS = ("generate", "verify", "animate")
EXECUTION_PROFILES = (
    "none",
    "local-tiny-cpu",
    "remote-gpu-hf",
    "generator-sdxl-gpu",
    "generator-pixart-gpu",
)
DEFAULT_JOB_SPEC_DIR = Path(__file__).resolve().parent / "job_specs"

def _sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip("-").lower()
    return cleaned or "default"


def _default_config_name(command: str) -> str:
    return {
        "gen-verify": "gen_verify",
        "verify-only": "verify_only",
        "replay-eval": "replay_eval",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]


def _mapped_command(command: str) -> str:
    mapped = {
        "gen-verify": "generate",
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]
    return mapped


def _flow_kind_for_command(command: str) -> str:
    return {
        "gen-verify": DEFAULT_FLOW_KIND,
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]


def _parse_kv_pairs(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise SystemExit(f"invalid KEY=VALUE pair: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"invalid KEY=VALUE pair: {raw}")
        out[key] = value
    return out


def _normalize_api_url(url: str) -> str:
    value = url.rstrip("/")
    if value.endswith("/api"):
        return value
    return f"{value}/api"


def _extra_headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": "discoverex-job-register/1.0",
    }
    cf_id = (
        SETTINGS.prefect_cf_access_client_id or SETTINGS.cf_access_client_id
    ).strip()
    cf_secret = (
        SETTINGS.prefect_cf_access_client_secret or SETTINGS.cf_access_client_secret
    ).strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _client_httpx_settings() -> dict[str, dict[str, str]]:
    return {"headers": _extra_headers()}


def _find_deployment(client: SyncPrefectClient, name: str) -> Any:
    rows = client.read_deployments(
        deployment_filter=DeploymentFilter(name=DeploymentFilterName(any_=[name])),
        limit=20,
    )
    for row in rows:
        if str(getattr(row, "name", "")) == name and getattr(row, "id", None):
            return row
    raise SystemExit(f"deployment not found: {name}")


def _create_flow_run(
    client: SyncPrefectClient,
    deployment_id: UUID,
    parameters: dict[str, Any],
    flow_run_name: str | None,
    work_queue_name: str | None = None,
) -> Any:
    return client.create_flow_run_from_deployment(
        deployment_id,
        parameters=parameters,
        name=flow_run_name,
        work_queue_name=work_queue_name,
    )


def _emit_prefect_diagnostics(api_url: str, deployment_name: str) -> None:
    headers = _extra_headers()
    print(
        "[discoverex-register] prefect submission failed",
        file=sys.stderr,
    )
    print(
        f"[discoverex-register] api_url={api_url} deployment={deployment_name}",
        file=sys.stderr,
    )
    print(
        "[discoverex-register] cf_access_headers="
        f"{'enabled' if 'CF-Access-Client-Id' in headers else 'missing'} "
        f"(prefect_cf={'set' if SETTINGS.prefect_cf_access_client_id else 'unset'}, "
        f"cf={'set' if SETTINGS.cf_access_client_id else 'unset'})",
        file=sys.stderr,
    )
    print(
        "[discoverex-register] likely cause: Prefect API responded with HTML "
        "login/challenge page instead of JSON. Check Cloudflare Access tokens "
        "and PREFECT_API_URL.",
        file=sys.stderr,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build orchestrator job_spec_json and submit a real flow run "
            "to a Prefect deployment."
        )
    )
    parser.add_argument("--prefect-api-url", default=SETTINGS.prefect_api_url)
    parser.add_argument("--deployment", default=None)
    parser.add_argument("--engine", default="discoverex")
    parser.add_argument("--run-mode", choices=("repo", "inline"), default="inline")
    parser.add_argument("--repo-url", default=SETTINGS.engine_repo_url)
    parser.add_argument("--ref", default=SETTINGS.engine_repo_ref or "main")
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--outputs-prefix", default=None)
    parser.add_argument("--contract-version", choices=("v1", "v2"), default="v2")
    parser.add_argument(
        "--execution-profile",
        choices=EXECUTION_PROFILES,
        default="none",
    )
    parser.add_argument("--command", required=True)
    parser.add_argument("--config-name", default=None)
    parser.add_argument("--config-dir", default="conf")
    parser.add_argument("--background-asset-ref", default=None)
    parser.add_argument("--background-prompt", default=None)
    parser.add_argument("--background-negative-prompt", default=None)
    parser.add_argument("--object-prompt", default=None)
    parser.add_argument("--object-negative-prompt", default=None)
    parser.add_argument("--final-prompt", default=None)
    parser.add_argument("--final-negative-prompt", default=None)
    parser.add_argument("--scene-json", default=None)
    parser.add_argument("--scene-jsons", action="append", default=[])
    parser.add_argument("--override", "-o", action="append", default=[])
    parser.add_argument(
        "--bootstrap-mode",
        choices=("auto", "uv", "pip", "none"),
        default="none",
    )
    parser.add_argument("--runtime-extra", action="append", default=[])
    parser.add_argument("--runtime-env", action="append", default=[])
    parser.add_argument("--runner-env", action="append", default=[])
    parser.add_argument(
        "--mlflow-tracking-uri", default=SETTINGS.mlflow_tracking_uri or None
    )
    parser.add_argument(
        "--mlflow-s3-endpoint-url",
        default=SETTINGS.mlflow_s3_endpoint_url or None,
    )
    parser.add_argument(
        "--aws-access-key-id",
        default=(SETTINGS.aws_access_key_id or SETTINGS.minio_access_key) or None,
    )
    parser.add_argument(
        "--aws-secret-access-key",
        default=(SETTINGS.aws_secret_access_key or SETTINGS.minio_secret_key) or None,
    )
    parser.add_argument("--artifact-bucket", default=SETTINGS.artifact_bucket or None)
    parser.add_argument("--metadata-db-url", default=SETTINGS.metadata_db_url or None)
    parser.add_argument(
        "--cf-access-client-id",
        default=SETTINGS.cf_access_client_id or None,
    )
    parser.add_argument(
        "--cf-access-client-secret",
        default=SETTINGS.cf_access_client_secret or None,
    )
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _validate_command(args: argparse.Namespace) -> None:
    allowed = V1_COMMANDS if args.contract_version == "v1" else V2_COMMANDS
    if args.command not in allowed:
        raise SystemExit(
            f"--command={args.command} is invalid for contract_version={args.contract_version}"
        )


def _build_engine_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.command in {"gen-verify", "generate"}:
        if not args.background_asset_ref and not args.background_prompt:
            raise SystemExit(
                "--background-asset-ref or --background-prompt "
                f"is required for command={args.command}"
            )
        return {
            key: value
            for key, value in {
                "background_asset_ref": args.background_asset_ref,
                "background_prompt": args.background_prompt,
                "background_negative_prompt": args.background_negative_prompt,
                "object_prompt": args.object_prompt,
                "object_negative_prompt": args.object_negative_prompt,
                "final_prompt": args.final_prompt,
                "final_negative_prompt": args.final_negative_prompt,
            }.items()
            if value is not None
        }
    if args.command in {"verify-only", "verify"}:
        if not args.scene_json:
            raise SystemExit(f"--scene-json is required for command={args.command}")
        return {"scene_json": args.scene_json}
    if args.command == "replay-eval":
        if not args.scene_jsons:
            raise SystemExit(
                "--scene-jsons is required at least once for command=replay-eval"
            )
        return {"scene_jsons": args.scene_jsons}
    if args.command == "animate":
        return {"scene_jsons": args.scene_jsons} if args.scene_jsons else {}
    raise SystemExit(f"unsupported command: {args.command}")


def _build_profile_overrides(args: argparse.Namespace) -> list[str]:
    overrides: list[str] = _worker_runtime_adapter_overrides(args)
    if args.execution_profile == "local-tiny-cpu":
        overrides.extend(
            [
                "runtime/model_runtime=cpu",
                "runtime.width=256",
                "runtime.height=256",
                "models/background_generator=tiny_sd_cpu",
                "models/hidden_region=tiny_torch",
                "models/inpaint=tiny_torch",
                "models/perception=tiny_torch",
                "models/fx=tiny_sd_cpu",
            ]
        )
    elif args.execution_profile == "remote-gpu-hf":
        overrides.extend(
            [
                "runtime/model_runtime=gpu",
                "models/background_generator=hf",
                "models/hidden_region=hf",
                "models/inpaint=hf",
                "models/perception=hf",
                "models/fx=hf",
            ]
        )
    elif args.execution_profile == "generator-sdxl-gpu":
        overrides.extend(
            [
                "runtime/model_runtime=gpu",
                "runtime.width=512",
                "runtime.height=512",
                "models/background_generator=sdxl_gpu",
                "models/hidden_region=hf",
                "models/inpaint=sdxl_gpu",
                "models/perception=hf",
                "models/fx=copy_image",
            ]
        )
    elif args.execution_profile == "generator-pixart-gpu":
        overrides.extend(
            [
                "profile=generator_pixart_gpu_v2_8gb",
                "runtime/model_runtime=gpu",
                "flows/generate=v2",
                "runtime.width=1024",
                "runtime.height=1024",
                "models/background_generator=pixart_sigma_8gb",
                "models/object_generator=layerdiffuse",
                "models/hidden_region=hf",
                "models/inpaint=sdxl_gpu_similarity_v2",
                "models/perception=hf",
                "models/fx=copy_image",
                "runtime.model_runtime.offload_mode=sequential",
            ]
        )
    return overrides


def _worker_runtime_adapter_overrides(args: argparse.Namespace) -> list[str]:
    runtime_mode = str(getattr(args, "run_mode", "")).strip()
    if runtime_mode != "inline":
        return []
    return [
        "adapters/artifact_store=local",
        "adapters/tracker=mlflow_server",
    ]


def _build_runtime_env(args: argparse.Namespace) -> dict[str, str]:
    return _parse_kv_pairs(args.runtime_env)


def _build_runner_env(args: argparse.Namespace) -> dict[str, str]:
    env = _parse_kv_pairs(args.runner_env)
    optional_env = {
        "CF_ACCESS_CLIENT_ID": args.cf_access_client_id,
        "CF_ACCESS_CLIENT_SECRET": args.cf_access_client_secret,
    }
    for key, value in optional_env.items():
        if value:
            env[key] = value
    return env


def _build_runtime_extras(args: argparse.Namespace) -> list[str]:
    extras = [item.strip() for item in args.runtime_extra if item.strip()]
    if not extras:
        extras = ["tracking", "storage"]
    profile_extras: list[str] = []
    if args.execution_profile == "local-tiny-cpu":
        profile_extras.append("ml-cpu")
    elif args.execution_profile in {
        "remote-gpu-hf",
        "generator-sdxl-gpu",
        "generator-pixart-gpu",
    }:
        profile_extras.append("ml-gpu")
    for extra in profile_extras:
        if extra not in extras:
            extras.append(extra)
    return extras


def _build_job_spec(args: argparse.Namespace) -> JobSpec:
    if args.run_mode == "repo" and (not args.repo_url or not args.ref):
        raise SystemExit("--repo-url and --ref are required when --run-mode=repo")
    _validate_command(args)

    runtime_extras = _build_runtime_extras(args)
    overrides = [*_build_profile_overrides(args), *args.override]
    _validate_worker_runtime_overrides(
        overrides=overrides,
        run_mode=args.run_mode,
    )
    flow_kind = _flow_kind_for_command(args.command)
    entrypoint = [flow_entrypoint_for_kind(flow_kind)]
    inputs: JobSpecInputs = {
        "contract_version": args.contract_version,
        "command": args.command,
        "config_name": _resolved_config_name(args),
        "config_dir": args.config_dir,
        "args": _build_engine_args(args),
        "overrides": overrides,
        "runtime": {
            "mode": "worker",
            "bootstrap_mode": args.bootstrap_mode,
            "extras": runtime_extras,
            "extra_env": _build_runtime_env(args),
            "repo_strategy": "none",
            "deps_strategy": "none",
            "workspace_strategy": "reuse",
        },
    }
    return {
        "run_mode": args.run_mode,
        "engine": args.engine,
        "repo_url": args.repo_url if args.run_mode == "repo" else None,
        "ref": args.ref if args.run_mode == "repo" else None,
        "entrypoint": entrypoint,
        "config": None,
        "job_name": _resolved_job_name(args),
        "inputs": inputs,
        "env": _build_runner_env(args),
        "outputs_prefix": args.outputs_prefix,
    }


def _validate_worker_runtime_overrides(
    *,
    overrides: list[str],
    run_mode: str,
) -> None:
    if run_mode != "inline":
        return
    artifact_store = _override_value(overrides, "adapters/artifact_store")
    if artifact_store and artifact_store != "local":
        raise SystemExit(
            "worker runtime requires adapters/artifact_store=local"
        )
    tracker = _override_value(overrides, "adapters/tracker")
    if tracker and tracker != "mlflow_server":
        raise SystemExit("worker runtime requires adapters/tracker=mlflow_server")


def _override_value(overrides: list[str], key: str) -> str | None:
    prefix = f"{key}="
    for raw in reversed(overrides):
        if raw.startswith(prefix):
            return raw.removeprefix(prefix).strip()
    return None


def _resolved_config_name(args: argparse.Namespace) -> str:
    value = str(args.config_name or "").strip()
    if value:
        return value
    return _default_config_name(args.command)


def _resolved_deployment_name(args: argparse.Namespace) -> str:
    explicit = str(args.deployment or "").strip()
    if explicit:
        return explicit
    return deployment_name_for_purpose(
        SETTINGS.register_deployment_purpose or "standard",
        flow_kind=_flow_kind_for_command(args.command),
    )


def _resolved_job_name(args: argparse.Namespace) -> str:
    explicit = str(args.job_name or "").strip()
    if explicit:
        return explicit
    command = _sanitize_name(_mapped_command(args.command))
    config_name = _sanitize_name(_resolved_config_name(args))
    profile = _sanitize_name(args.execution_profile)
    return f"{command}--{config_name}--{profile}"


def _resolved_deployment_name_from_job_spec(
    job_spec: JobSpec | dict[str, Any],
    explicit_deployment: str | None = None,
) -> str:
    explicit = str(explicit_deployment or "").strip()
    if explicit:
        return explicit
    # job_spec inputs/engine_run are optional, need safe access or assuming presence
    inputs = job_spec.get("inputs", {})
    command = str(inputs.get("command", "")).strip()
    # Fallback to engine_run if inputs missing? JobSpec doesn't have engine_run anymore.

    if not command:
        return deployment_name_for_purpose(
            SETTINGS.register_deployment_purpose or "standard"
        )
    return deployment_name_for_purpose(
        SETTINGS.register_deployment_purpose or "standard",
        flow_kind=_flow_kind_for_command(command),
    )


def _extract_job_inputs(job_spec: JobSpec | dict[str, Any]) -> dict[str, Any]:
    payload = job_spec.get("inputs")
    if isinstance(payload, dict):
        return dict(payload)
    payload = job_spec.get("engine_run")
    if isinstance(payload, dict):
        return dict(payload)
    raise SystemExit("job spec requires inputs")


def _resolve_job_spec_config(job_spec: JobSpec | dict[str, Any]) -> dict[str, Any]:
    from discoverex.config_loader import resolve_pipeline_config

    inputs = _extract_job_inputs(job_spec)
    resolved = resolve_pipeline_config(
        config_name=str(inputs.get("config_name") or "").strip()
        or _default_config_name(str(inputs.get("command") or "").strip()),
        config_dir=str(inputs.get("config_dir") or "conf"),
        overrides=[str(item) for item in inputs.get("overrides", [])],
        resolved_config=inputs.get("resolved_config"),
    )
    return resolved.model_dump(mode="python")


def _enrich_job_spec_with_resolved_config(
    job_spec: JobSpec | dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(job_spec)
    inputs = dict(_extract_job_inputs(job_spec))
    if inputs.get("resolved_config") is None:
        inputs["resolved_config"] = _resolve_job_spec_config(job_spec)
    enriched["inputs"] = inputs
    return enriched


def submit_job_spec(
    *,
    job_spec: JobSpec,
    prefect_api_url: str,
    deployment: str | None = None,
    job_name: str | None = None,
    work_queue_name: str | None = None,
    resume_key: str | None = None,
    checkpoint_dir: str | None = None,
) -> dict[str, Any]:
    if not prefect_api_url:
        raise SystemExit("--prefect-api-url is required unless PREFECT_API_URL is set")
    api_url = _normalize_api_url(prefect_api_url)
    enriched_job_spec = _enrich_job_spec_with_resolved_config(job_spec)
    deployment_name = _resolved_deployment_name_from_job_spec(
        enriched_job_spec, deployment
    )
    params: dict[str, Any] = {
        "job_spec_json": json.dumps(enriched_job_spec, ensure_ascii=True),
        "resume_key": resume_key,
        "checkpoint_dir": checkpoint_dir,
    }
    with temporary_settings(updates={PREFECT_API_URL: api_url}):
        with get_client(
            sync_client=True,
            httpx_settings=_client_httpx_settings(),
        ) as client:
            try:
                deployment_row = _find_deployment(client, deployment_name)
                deployment_id = UUID(str(deployment_row.id))
                created = _create_flow_run(
                    client,
                    deployment_id,
                    params,
                    job_name
                    or str(enriched_job_spec.get("job_name", "")).strip()
                    or None,
                    work_queue_name,
                )
            except json.JSONDecodeError as exc:
                _emit_prefect_diagnostics(api_url, deployment_name)
                raise SystemExit(
                    "Prefect client expected JSON but received a non-JSON response. "
                    "Most likely Cloudflare Access blocked the request."
                ) from exc
    return {
        "ok": True,
        "deployment": deployment_name,
        "deployment_id": str(deployment_id),
        "flow_run_id": str(getattr(created, "id", "")),
        "flow_run_name": getattr(created, "name", None),
        "work_queue_name": work_queue_name,
        "engine": job_spec.get("engine"),
        "run_mode": job_spec.get("run_mode"),
    }


def write_job_spec(
    job_spec: JobSpec,
    output_file: str | Path | None = None,
) -> Path:
    target = (
        Path(output_file)
        if output_file
        else DEFAULT_JOB_SPEC_DIR
        / (f"{str(job_spec.get('job_name', '')).strip() or 'job'}.yaml")
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(job_spec, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    args = _build_parser().parse_args()
    job_spec = _build_job_spec(args)

    if args.dry_run:
        print(json.dumps(job_spec, ensure_ascii=True))
        return 0

    output = submit_job_spec(
        job_spec=job_spec,
        prefect_api_url=args.prefect_api_url,
        deployment=_resolved_deployment_name(args),
        job_name=_resolved_job_name(args),
        resume_key=args.resume_key,
        checkpoint_dir=args.checkpoint_dir,
    )
    print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
