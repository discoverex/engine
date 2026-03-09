#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib import error, request

DEFAULT_ENTRYPOINT = [
    "/bin/sh",
    "-lc",
    "PYTHONPATH=src python -m discoverex.orchestrator_contract.launcher",
]

V1_COMMANDS = ("gen-verify", "verify-only", "replay-eval")
V2_COMMANDS = ("generate", "verify", "animate")
EXECUTION_PROFILES = (
    "none",
    "local-tiny-cpu",
    "remote-gpu-hf",
    "generator-sdxl-gpu",
)


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


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "discoverex-job-register/1.0",
        "Content-Type": "application/json",
    }
    cf_id = os.getenv("PREFECT_CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("PREFECT_CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _http_json(
    method: str,
    api_url: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        f"{api_url}/{path.lstrip('/')}",
        method=method,
        data=body,
        headers=_headers(),
    )
    try:
        with request.urlopen(req, timeout=30) as resp:  # nosec B310
            raw = resp.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _find_deployment_id(api_url: str, name: str) -> str:
    rows = _http_json(
        "POST",
        api_url,
        "deployments/filter",
        {
            "sort": "NAME_ASC",
            "limit": 20,
            "offset": 0,
            "deployments": {"name": {"any_": [name]}},
        },
    )
    if not isinstance(rows, list):
        raise SystemExit("unexpected deployments/filter response shape")
    for row in rows:
        if str(row.get("name", "")) == name and row.get("id"):
            return str(row["id"])
    raise SystemExit(f"deployment not found: {name}")


def _create_flow_run(
    api_url: str,
    deployment_id: str,
    parameters: dict[str, Any],
    flow_run_name: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"parameters": parameters}
    if flow_run_name:
        payload["name"] = flow_run_name
    row = _http_json(
        "POST",
        api_url,
        f"deployments/{deployment_id}/create_flow_run",
        payload,
    )
    if not isinstance(row, dict):
        raise SystemExit("unexpected create_flow_run response shape")
    return row


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build orchestrator job_spec_json and submit a real flow run "
            "to a Prefect deployment."
        )
    )
    parser.add_argument("--prefect-api-url", default=os.getenv("PREFECT_API_URL", ""))
    parser.add_argument("--deployment", default="engine-run")
    parser.add_argument("--engine", default="discoverex")
    parser.add_argument("--run-mode", choices=("repo", "inline"), default="repo")
    parser.add_argument("--repo-url", default=os.getenv("ENGINE_REPO_URL", ""))
    parser.add_argument("--ref", default=os.getenv("ENGINE_REPO_REF", "main"))
    parser.add_argument("--entrypoint-shell-command", default=None)
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--outputs-prefix", default=None)
    parser.add_argument("--contract-version", choices=("v1", "v2"), default="v2")
    parser.add_argument(
        "--execution-profile",
        choices=EXECUTION_PROFILES,
        default="none",
    )
    parser.add_argument("--command", required=True)
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
        choices=("auto", "uv", "pip"),
        default="auto",
    )
    parser.add_argument("--runtime-extra", action="append", default=[])
    parser.add_argument("--runtime-env", action="append", default=[])
    parser.add_argument("--runner-env", action="append", default=[])
    parser.add_argument("--mlflow-tracking-uri", default=None)
    parser.add_argument("--mlflow-s3-endpoint-url", default=None)
    parser.add_argument("--aws-access-key-id", default=None)
    parser.add_argument("--aws-secret-access-key", default=None)
    parser.add_argument("--artifact-bucket", default=None)
    parser.add_argument("--metadata-db-url", default=None)
    parser.add_argument("--cf-access-client-id", default=None)
    parser.add_argument("--cf-access-client-secret", default=None)
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
    overrides: list[str] = []
    if args.execution_profile != "none":
        overrides.extend(
            [
                "adapters/artifact_store=minio",
                "adapters/tracker=mlflow_server",
            ]
        )
        if args.metadata_db_url:
            overrides.append("adapters/metadata_store=postgres")
    if args.execution_profile == "local-tiny-cpu":
        overrides.extend(
            [
                "runtime/model_runtime=cpu",
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
                "models/background_generator=sdxl_gpu",
                "models/hidden_region=hf",
                "models/inpaint=sdxl_gpu",
                "models/perception=hf",
                "models/fx=sdxl_gpu",
            ]
        )
    return overrides


def _build_runtime_env(args: argparse.Namespace) -> dict[str, str]:
    env = _parse_kv_pairs(args.runtime_env)
    optional_env = {
        "MLFLOW_TRACKING_URI": args.mlflow_tracking_uri,
        "MLFLOW_S3_ENDPOINT_URL": args.mlflow_s3_endpoint_url,
        "AWS_ACCESS_KEY_ID": args.aws_access_key_id,
        "AWS_SECRET_ACCESS_KEY": args.aws_secret_access_key,
        "ARTIFACT_BUCKET": args.artifact_bucket,
        "METADATA_DB_URL": args.metadata_db_url,
    }
    for key, value in optional_env.items():
        if value:
            env[key] = value
    return env


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
    elif args.execution_profile == "remote-gpu-hf":
        profile_extras.append("ml-gpu")
    for extra in profile_extras:
        if extra not in extras:
            extras.append(extra)
    return extras


def _build_job_spec(args: argparse.Namespace) -> dict[str, Any]:
    if args.run_mode == "repo" and (not args.repo_url or not args.ref):
        raise SystemExit("--repo-url and --ref are required when --run-mode=repo")
    _validate_command(args)

    runtime_extras = _build_runtime_extras(args)
    overrides = [*_build_profile_overrides(args), *args.override]
    entrypoint = DEFAULT_ENTRYPOINT
    if args.entrypoint_shell_command:
        entrypoint = ["/bin/sh", "-lc", args.entrypoint_shell_command]

    inputs = {
        "contract_version": args.contract_version,
        "command": args.command,
        "args": _build_engine_args(args),
        "overrides": overrides,
        "runtime": {
            "mode": "worker",
            "bootstrap_mode": args.bootstrap_mode,
            "extras": runtime_extras,
            "extra_env": _build_runtime_env(args),
        },
    }
    return {
        "run_mode": args.run_mode,
        "engine": args.engine,
        "repo_url": args.repo_url if args.run_mode == "repo" else None,
        "ref": args.ref if args.run_mode == "repo" else None,
        "entrypoint": entrypoint,
        "config": None,
        "job_name": args.job_name,
        "inputs": inputs,
        "env": _build_runner_env(args),
        "outputs_prefix": args.outputs_prefix,
    }


def main() -> int:
    args = _build_parser().parse_args()
    job_spec = _build_job_spec(args)

    if args.dry_run:
        print(json.dumps(job_spec, ensure_ascii=True, indent=2))
        return 0

    if not args.prefect_api_url:
        raise SystemExit("--prefect-api-url is required unless PREFECT_API_URL is set")
    api_url = _normalize_api_url(args.prefect_api_url)
    deployment_id = _find_deployment_id(api_url, args.deployment)
    params: dict[str, Any] = {
        "job_spec_json": json.dumps(job_spec, ensure_ascii=True),
        "resume_key": args.resume_key,
        "checkpoint_dir": args.checkpoint_dir,
    }
    created = _create_flow_run(api_url, deployment_id, params, args.job_name)
    output = {
        "ok": True,
        "deployment": args.deployment,
        "deployment_id": deployment_id,
        "flow_run_id": created.get("id"),
        "flow_run_name": created.get("name"),
        "engine": job_spec["engine"],
        "run_mode": job_spec["run_mode"],
    }
    print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
