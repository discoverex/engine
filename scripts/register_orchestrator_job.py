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
    "python -m discoverex.orchestrator_contract.launcher",
]


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
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--outputs-prefix", default=None)
    parser.add_argument(
        "--command", required=True, choices=("gen-verify", "verify-only", "replay-eval")
    )
    parser.add_argument("--background-asset-ref", default=None)
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
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _build_engine_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "gen-verify":
        if not args.background_asset_ref:
            raise SystemExit(
                "--background-asset-ref is required for command=gen-verify"
            )
        return {"background_asset_ref": args.background_asset_ref}
    if args.command == "verify-only":
        if not args.scene_json:
            raise SystemExit("--scene-json is required for command=verify-only")
        return {"scene_json": args.scene_json}
    if not args.scene_jsons:
        raise SystemExit(
            "--scene-jsons is required at least once for command=replay-eval"
        )
    return {"scene_jsons": args.scene_jsons}


def _build_job_spec(args: argparse.Namespace) -> dict[str, Any]:
    if args.run_mode == "repo" and (not args.repo_url or not args.ref):
        raise SystemExit("--repo-url and --ref are required when --run-mode=repo")
    runtime_extras = [item.strip() for item in args.runtime_extra if item.strip()]
    if not runtime_extras:
        runtime_extras = ["tracking", "storage"]

    inputs = {
        "contract_version": "v1",
        "command": args.command,
        "args": _build_engine_args(args),
        "overrides": args.override,
        "runtime": {
            "mode": "worker",
            "bootstrap_mode": args.bootstrap_mode,
            "extras": runtime_extras,
            "extra_env": _parse_kv_pairs(args.runtime_env),
        },
    }
    return {
        "run_mode": args.run_mode,
        "engine": args.engine,
        "repo_url": args.repo_url if args.run_mode == "repo" else None,
        "ref": args.ref if args.run_mode == "repo" else None,
        "entrypoint": DEFAULT_ENTRYPOINT,
        "config": None,
        "job_name": args.job_name,
        "inputs": inputs,
        "env": _parse_kv_pairs(args.runner_env),
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
