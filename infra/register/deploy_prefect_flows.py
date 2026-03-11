#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
from typing import Any, cast

from prefect.deployments.runner import RunnerDeployment
from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_CLIENT_CUSTOM_HEADERS,
    temporary_settings,
)
from register_orchestrator_job import _extra_headers
from settings import SETTINGS

from discoverex.application.flows import run_engine_job_flow


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register engine-owned Prefect deployments."
    )
    parser.add_argument("--prefect-api-url", default=SETTINGS.prefect_api_url)
    parser.add_argument("--work-pool-name", default=SETTINGS.prefect_work_pool)
    return parser


def _apply_deployments(work_pool_name: str) -> dict[str, str]:
    return {
        "run-engine-job": str(
            _to_runner_deployment(
                run_engine_job_flow.to_deployment(
                    name="run-engine-job",
                    work_pool_name=work_pool_name,
                )
            ).apply(work_pool_name=work_pool_name)
        )
    }


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
        output = _apply_deployments(args.work_pool_name)
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
