#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypedDict, cast

from prefect.settings import PREFECT_API_URL, temporary_settings

from infra.register.branch_deployments import (
    DEFAULT_FLOW_KIND,
    SUPPORTED_FLOW_KINDS,
    deployment_name_for_branch,
    flow_entrypoint_for_kind,
)
from infra.register.register_orchestrator_job import _extra_headers, _normalize_api_url
from infra.register.settings import SETTINGS, default_deployment_version


class DeploymentMetadata(TypedDict, total=False):
    deployment_name: str
    deployment_id: str
    engine: str
    flow_kind: str
    branch: str
    repo_url: str
    ref: str
    entrypoint: str
    work_pool_name: str
    work_queue_name: str
    deployment_version: str
    deployment_suffix: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Register an embedded-source Prefect deployment for an engine flow kind."
        )
    )
    parser.add_argument("--engine", default=SETTINGS.engine_name)
    parser.add_argument("--branch", required=True)
    parser.add_argument(
        "--flow-kind", choices=SUPPORTED_FLOW_KINDS, default=DEFAULT_FLOW_KIND
    )
    parser.add_argument("--prefect-api-url", default=SETTINGS.prefect_api_url)
    parser.add_argument("--work-pool-name", default=SETTINGS.prefect_work_pool)
    parser.add_argument("--flow-entrypoint", default=None)
    parser.add_argument("--repo-url", default=SETTINGS.engine_repo_url)
    parser.add_argument("--ref", default=None)
    parser.add_argument("--deployment-name", default=None)
    parser.add_argument("--deployment-suffix", default="")
    parser.add_argument(
        "--deployment-version",
        default=default_deployment_version(),
    )
    parser.add_argument("--work-queue-name", default=SETTINGS.prefect_work_queue)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _resolved_entrypoint(flow_kind: str, cli_value: str | None) -> str:
    explicit = str(cli_value or "").strip()
    if explicit:
        return explicit
    return flow_entrypoint_for_kind(flow_kind)


def _deployment_metadata(
    *,
    engine: str,
    flow_kind: str,
    branch: str,
    repo_url: str,
    ref: str,
    flow_entrypoint: str,
    work_pool_name: str,
    work_queue_name: str,
    deployment_version: str,
    deployment_name: str | None,
    deployment_suffix: str,
) -> DeploymentMetadata:
    resolved_name = str(deployment_name or "").strip() or deployment_name_for_branch(
        branch,
        flow_kind=flow_kind,
        engine=engine,
        suffix=deployment_suffix,
    )
    return {
        "deployment_name": resolved_name,
        "engine": engine,
        "flow_kind": flow_kind,
        "branch": branch,
        "repo_url": repo_url,
        "ref": ref,
        "entrypoint": flow_entrypoint,
        "work_pool_name": work_pool_name,
        "work_queue_name": work_queue_name,
        "deployment_version": deployment_version,
        "deployment_suffix": deployment_suffix,
    }


def _resolved_ref(branch: str, ref: str | None) -> str:
    explicit = str(ref or "").strip()
    if explicit:
        return explicit
    return branch


@contextmanager
def _prefect_settings(prefect_api_url: str) -> Iterator[None]:
    api_url = _normalize_api_url(prefect_api_url)
    previous_headers = os.environ.get("PREFECT_CLIENT_CUSTOM_HEADERS")
    os.environ["PREFECT_CLIENT_CUSTOM_HEADERS"] = json.dumps(_extra_headers())
    try:
        with temporary_settings(updates={PREFECT_API_URL: api_url}):
            yield None
    finally:
        if previous_headers is None:
            os.environ.pop("PREFECT_CLIENT_CUSTOM_HEADERS", None)
        else:
            os.environ["PREFECT_CLIENT_CUSTOM_HEADERS"] = previous_headers


def _load_flow(entrypoint: str) -> Any:
    module_name, attr_name = entrypoint.split(":", 1)
    if module_name.endswith(".py"):
        module_name = module_name[:-3]
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _deploy_embedded_flow(
    *,
    engine: str,
    flow_kind: str,
    branch: str,
    flow_entrypoint: str,
    work_pool_name: str,
    work_queue_name: str,
    image: str,
    deployment_version: str,
    deployment_name: str,
    deployment_suffix: str,
) -> str:
    embedded_flow = cast(Any, _load_flow(flow_entrypoint))
    deployment_id = embedded_flow.deploy(
        name=deployment_name,
        work_pool_name=work_pool_name,
        image=image,
        work_queue_name=work_queue_name,
        job_variables={},
        build=False,
        push=False,
        description=f"Execute the {flow_kind} flow for branch {branch!r}.",
        tags=[engine, flow_kind, branch],
        version=deployment_version,
        print_next_steps=False,
    )
    return str(deployment_id)


def main() -> int:
    args = _build_parser().parse_args()
    if not args.prefect_api_url:
        raise SystemExit("--prefect-api-url is required unless PREFECT_API_URL is set")
    deployment: DeploymentMetadata = _deployment_metadata(
        engine=args.engine,
        flow_kind=args.flow_kind,
        branch=args.branch,
        repo_url=args.repo_url,
        ref=_resolved_ref(args.branch, args.ref),
        flow_entrypoint=_resolved_entrypoint(args.flow_kind, args.flow_entrypoint),
        work_pool_name=args.work_pool_name,
        work_queue_name=args.work_queue_name,
        deployment_version=args.deployment_version,
        deployment_name=args.deployment_name,
        deployment_suffix=args.deployment_suffix,
    )
    if args.dry_run:
        print(json.dumps(deployment, ensure_ascii=True))
        return 0
    with _prefect_settings(args.prefect_api_url):
        deployment["deployment_id"] = _deploy_embedded_flow(
            engine=args.engine,
            flow_kind=args.flow_kind,
            branch=args.branch,
            flow_entrypoint=deployment["entrypoint"],
            work_pool_name=args.work_pool_name,
            work_queue_name=args.work_queue_name,
            image=SETTINGS.prefect_work_image,
            deployment_version=args.deployment_version,
            deployment_name=deployment["deployment_name"],
            deployment_suffix=args.deployment_suffix,
        )
    print(json.dumps(deployment, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
