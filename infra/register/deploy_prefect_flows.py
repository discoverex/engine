#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any, cast

from prefect.deployments.runner import RunnerDeployment
from prefect.runner.storage import GitRepository
from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_CLIENT_CUSTOM_HEADERS,
    temporary_settings,
)
from register_orchestrator_job import _extra_headers
from settings import SETTINGS, default_deployment_version

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from infra.prefect.flow import run_job_flow


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compatibility helper for registering the engine flow into Prefect. "
            "The public operator contract is the flow entrypoint, not this script."
        )
    )
    parser.add_argument("--prefect-api-url", default=SETTINGS.prefect_api_url)
    parser.add_argument("--work-pool-name", default=SETTINGS.prefect_work_pool)
    parser.add_argument("--flow-source", default=SETTINGS.register_flow_source)
    parser.add_argument("--flow-entrypoint", default=SETTINGS.register_flow_entrypoint)
    parser.add_argument("--flow-ref", default=SETTINGS.register_flow_ref)
    parser.add_argument(
        "--deployment-version",
        default=default_deployment_version(),
    )
    parser.add_argument("--primary-name", default=SETTINGS.prefect_deployment)
    parser.add_argument("--primary-queue", default=SETTINGS.prefect_work_queue)
    parser.add_argument("--register-colab", action="store_true")
    parser.add_argument("--colab-name", default=SETTINGS.prefect_colab_deployment)
    parser.add_argument("--colab-queue", default=SETTINGS.prefect_colab_work_queue)
    parser.add_argument("--register-compat-aliases", action="store_true")
    parser.add_argument(
        "--compat-fixed-name", default=SETTINGS.prefect_compat_deployment
    )
    parser.add_argument(
        "--compat-fixed-queue", default=SETTINGS.prefect_compat_work_queue
    )
    parser.add_argument(
        "--compat-colab-name", default=SETTINGS.prefect_compat_colab_deployment
    )
    parser.add_argument(
        "--compat-colab-queue", default=SETTINGS.prefect_compat_colab_work_queue
    )
    return parser


def _apply_deployments(
    *,
    work_pool_name: str,
    flow_source: str,
    flow_entrypoint: str,
    flow_ref: str,
    deployment_version: str,
    primary_name: str,
    primary_queue: str,
    register_colab: bool,
    colab_name: str,
    colab_queue: str,
    register_compat_aliases: bool,
    compat_fixed_name: str,
    compat_fixed_queue: str,
    compat_colab_name: str,
    compat_colab_queue: str,
) -> dict[str, str]:
    registration_flow = _load_registration_flow(
        flow_source=flow_source,
        flow_entrypoint=flow_entrypoint,
        flow_ref=flow_ref,
    )
    deployments: list[tuple[str, str]] = [(primary_name, primary_queue)]
    if register_colab:
        deployments.append((colab_name, colab_queue))
    if register_compat_aliases:
        deployments.append((compat_fixed_name, compat_fixed_queue))
        if register_colab:
            deployments.append((compat_colab_name, compat_colab_queue))
    return {
        name: str(
            _to_runner_deployment(
                registration_flow.to_deployment(
                    name=name,
                    version=deployment_version,
                    work_pool_name=work_pool_name,
                    work_queue_name=queue_name,
                )
            ).apply(work_pool_name=work_pool_name)
        )
        for name, queue_name in deployments
    }


def _load_registration_flow(
    *, flow_source: str, flow_entrypoint: str, flow_ref: str
) -> Any:
    source: str | GitRepository
    if "://" in flow_source or flow_source.startswith("git@"):
        source = GitRepository(url=flow_source, branch=flow_ref or None)
    else:
        source = flow_source
    loaded = run_job_flow.from_source(source=source, entrypoint=flow_entrypoint)
    if inspect.isawaitable(loaded):
        return asyncio.run(cast(Any, loaded))
    return loaded


def _to_runner_deployment(
    deployment: RunnerDeployment | object,
) -> RunnerDeployment:
    if inspect.isawaitable(deployment):
        resolved: Any = asyncio.run(cast(Any, deployment))
    else:
        resolved = deployment
    if not isinstance(resolved, RunnerDeployment):
        raise TypeError("to_deployment() did not return a RunnerDeployment")
    return resolved


def main() -> int:
    args = _build_parser().parse_args()
    if not args.prefect_api_url:
        raise SystemExit("--prefect-api-url is required unless PREFECT_API_URL is set")
    with temporary_settings(
        updates={
            PREFECT_API_URL: args.prefect_api_url,
            PREFECT_CLIENT_CUSTOM_HEADERS: _extra_headers(),
        }
    ):
        output = _apply_deployments(
            work_pool_name=args.work_pool_name,
            flow_source=args.flow_source,
            flow_entrypoint=args.flow_entrypoint,
            flow_ref=args.flow_ref,
            deployment_version=args.deployment_version,
            primary_name=args.primary_name,
            primary_queue=args.primary_queue,
            register_colab=args.register_colab,
            colab_name=args.colab_name,
            colab_queue=args.colab_queue,
            register_compat_aliases=args.register_compat_aliases,
            compat_fixed_name=args.compat_fixed_name,
            compat_fixed_queue=args.compat_fixed_queue,
            compat_colab_name=args.compat_colab_name,
            compat_colab_queue=args.compat_colab_queue,
        )
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
