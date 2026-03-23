#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from infra.ops.branch_deployments import (
    DEFAULT_FLOW_KIND,
    deployment_name_for_purpose,
)
from infra.ops.settings import SETTINGS

ENGINE_ROOT = Path(__file__).resolve().parents[2]
LOW_LEVEL_MODULE = "infra.ops.register_orchestrator_job"


def _git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(ENGINE_ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _default_repo_url() -> str:
    return str(SETTINGS.engine_repo_url or _git_output("remote", "get-url", "origin"))


def _default_ref() -> str:
    return str(SETTINGS.engine_repo_ref or _git_output("branch", "--show-current"))


def _flow_kind_for_command(command: str) -> str:
    return {
        "gen-verify": DEFAULT_FLOW_KIND,
        "verify-only": "verify",
        "replay-eval": "animate",
        "generate": "generate",
        "verify": "verify",
        "animate": "animate",
    }[command]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compatibility helper that builds a job spec and submits it to an "
            "existing deployment. The public operator contract remains the "
            "registerable flow entrypoint."
        )
    )
    parser.add_argument("--prefect-api-url", default=SETTINGS.prefect_api_url)
    parser.add_argument("--deployment", default=None)
    parser.add_argument("--engine", default="discoverex")
    parser.add_argument("--run-mode", choices=("repo", "inline"), default="inline")
    parser.add_argument("--repo-url", default=_default_repo_url())
    parser.add_argument("--ref", default=_default_ref())
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--outputs-prefix", default=None)
    parser.add_argument("--contract-version", choices=("v1", "v2"), default="v2")
    parser.add_argument(
        "--execution-profile",
        choices=(
            "none",
            "local-tiny-cpu",
            "remote-gpu-hf",
            "generator-sdxl-gpu",
            "generator-pixart-gpu",
        ),
        default=SETTINGS.engine_execution_profile,
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
    parser.add_argument("--mlflow-tracking-uri", default=SETTINGS.mlflow_tracking_uri)
    parser.add_argument(
        "--mlflow-s3-endpoint-url",
        default=SETTINGS.mlflow_s3_endpoint_url,
    )
    parser.add_argument(
        "--aws-access-key-id",
        default=SETTINGS.aws_access_key_id or SETTINGS.minio_access_key,
    )
    parser.add_argument(
        "--aws-secret-access-key",
        default=SETTINGS.aws_secret_access_key or SETTINGS.minio_secret_key,
    )
    parser.add_argument("--artifact-bucket", default=SETTINGS.artifact_bucket)
    parser.add_argument("--metadata-db-url", default=SETTINGS.metadata_db_url)
    parser.add_argument(
        "--cf-access-client-id",
        default=SETTINGS.cf_access_client_id,
    )
    parser.add_argument(
        "--cf-access-client-secret",
        default=SETTINGS.cf_access_client_secret,
    )
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _append_option(argv: list[str], name: str, value: str | None) -> None:
    if value:
        argv.extend([name, value])


def _build_forward_argv(args: argparse.Namespace) -> list[str]:
    deployment = str(args.deployment or "").strip() or deployment_name_for_purpose(
        SETTINGS.register_deployment_purpose or "standard",
        flow_kind=_flow_kind_for_command(args.command),
    )
    argv = [
        sys.executable,
        "-m",
        LOW_LEVEL_MODULE,
        "--deployment",
        deployment,
        "--engine",
        args.engine,
        "--run-mode",
        args.run_mode,
        "--contract-version",
        args.contract_version,
        "--execution-profile",
        args.execution_profile,
        "--command",
        args.command,
        "--bootstrap-mode",
        args.bootstrap_mode,
    ]
    _append_option(argv, "--prefect-api-url", args.prefect_api_url)
    _append_option(argv, "--repo-url", args.repo_url)
    _append_option(argv, "--ref", args.ref)
    _append_option(argv, "--job-name", args.job_name)
    _append_option(argv, "--config-name", args.config_name)
    _append_option(argv, "--config-dir", args.config_dir)
    _append_option(argv, "--outputs-prefix", args.outputs_prefix)
    _append_option(argv, "--background-asset-ref", args.background_asset_ref)
    _append_option(argv, "--background-prompt", args.background_prompt)
    _append_option(
        argv, "--background-negative-prompt", args.background_negative_prompt
    )
    _append_option(argv, "--object-prompt", args.object_prompt)
    _append_option(argv, "--object-negative-prompt", args.object_negative_prompt)
    _append_option(argv, "--final-prompt", args.final_prompt)
    _append_option(argv, "--final-negative-prompt", args.final_negative_prompt)
    _append_option(argv, "--scene-json", args.scene_json)
    _append_option(argv, "--mlflow-tracking-uri", args.mlflow_tracking_uri)
    _append_option(argv, "--mlflow-s3-endpoint-url", args.mlflow_s3_endpoint_url)
    _append_option(argv, "--aws-access-key-id", args.aws_access_key_id)
    _append_option(argv, "--aws-secret-access-key", args.aws_secret_access_key)
    _append_option(argv, "--artifact-bucket", args.artifact_bucket)
    _append_option(argv, "--metadata-db-url", args.metadata_db_url)
    _append_option(argv, "--cf-access-client-id", args.cf_access_client_id)
    _append_option(argv, "--cf-access-client-secret", args.cf_access_client_secret)
    _append_option(argv, "--resume-key", args.resume_key)
    _append_option(argv, "--checkpoint-dir", args.checkpoint_dir)
    for value in args.scene_jsons:
        argv.extend(["--scene-jsons", value])
    for value in args.override:
        argv.extend(["--override", value])
    for value in args.runtime_extra:
        argv.extend(["--runtime-extra", value])
    for value in args.runtime_env:
        argv.extend(["--runtime-env", value])
    for value in args.runner_env:
        argv.extend(["--runner-env", value])
    if args.dry_run:
        argv.append("--dry-run")
    return argv


def main() -> int:
    args = _build_parser().parse_args()
    proc = subprocess.run(_build_forward_argv(args), check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
