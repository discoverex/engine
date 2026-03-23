#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import UUID

from prefect.client.orchestration import get_client
from prefect.client.schemas.actions import DeploymentUpdate
from prefect.settings import PREFECT_API_URL, temporary_settings

from infra.register.branch_deployments import (
    DEFAULT_FLOW_KIND,
    SUPPORTED_FLOW_KINDS,
    SUPPORTED_DEPLOYMENT_PURPOSES,
    default_queue_for_purpose,
    deployment_name_for_purpose,
    flow_entrypoint_for_kind,
)
from infra.register.register_orchestrator_job import _extra_headers, _normalize_api_url
from infra.register.settings import SETTINGS, default_deployment_version

class DeploymentMetadata(TypedDict, total=False):
    deployment_name: str
    deployment_id: str
    engine: str
    flow_kind: str
    purpose: str
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
    parser.add_argument(
        "--purpose",
        choices=SUPPORTED_DEPLOYMENT_PURPOSES,
        default=SETTINGS.register_deployment_purpose,
    )
    parser.add_argument("--branch", default="")
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
    parser.add_argument("--work-queue-name", default=None)
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
    purpose: str,
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
    resolved_name = str(deployment_name or "").strip() or deployment_name_for_purpose(
        purpose,
        flow_kind=flow_kind,
        engine=engine,
        suffix=deployment_suffix,
    )
    return {
        "deployment_name": resolved_name,
        "engine": engine,
        "flow_kind": flow_kind,
        "purpose": purpose,
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
    if str(branch).strip():
        return branch
    return SETTINGS.engine_repo_ref or "dev"


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


def _deployment_runtime_root() -> str:
    override = os.environ.get("DISCOVEREX_DEPLOY_RUNTIME_ROOT", "").strip()
    if override:
        return override
    return SETTINGS.prefect_work_runtime_dir


def _deployment_model_cache_root() -> str:
    override = os.environ.get("DISCOVEREX_DEPLOY_MODEL_CACHE_ROOT", "").strip()
    if override:
        return override
    return SETTINGS.prefect_work_model_cache_dir


def _deployment_job_variables(*, work_pool_name: str) -> dict[str, Any]:
    _validate_required_worker_env()
    process_working_dir = (
        os.environ.get("DISCOVEREX_DEPLOY_WORKING_DIR", "").strip() or "/app"
    )
    env_pairs = (
        ("PREFECT_API_URL", os.environ.get("PREFECT_API_URL", "")),
        (
            "PREFECT_CLIENT_CUSTOM_HEADERS",
            os.environ.get("PREFECT_CLIENT_CUSTOM_HEADERS", ""),
        ),
        ("CF_ACCESS_CLIENT_ID", os.environ.get("CF_ACCESS_CLIENT_ID", "")),
        (
            "CF_ACCESS_CLIENT_SECRET",
            os.environ.get("CF_ACCESS_CLIENT_SECRET", ""),
        ),
        ("STORAGE_API_URL", os.environ.get("STORAGE_API_URL", "")),
        ("MLFLOW_TRACKING_URI", os.environ.get("MLFLOW_TRACKING_URI", "")),
        (
            "MLFLOW_S3_ENDPOINT_URL",
            os.environ.get("MLFLOW_S3_ENDPOINT_URL", ""),
        ),
        ("AWS_ACCESS_KEY_ID", os.environ.get("AWS_ACCESS_KEY_ID", "")),
        (
            "AWS_SECRET_ACCESS_KEY",
            os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        ),
        ("ARTIFACT_BUCKET", os.environ.get("ARTIFACT_BUCKET", "")),
        ("DISCOVEREX_WORKER_RUNTIME_DIR", "/var/lib/discoverex"),
        ("DISCOVEREX_CACHE_DIR", "/var/lib/discoverex/cache"),
        ("MODEL_CACHE_DIR", "/var/lib/discoverex/cache/models"),
        ("UV_CACHE_DIR", "/var/lib/discoverex/cache/uv"),
        ("HF_HOME", "/var/lib/discoverex/cache/models/hf"),
        ("HF_TOKEN", os.environ.get("HF_TOKEN", "")),
        (
            "HUGGINGFACE_HUB_TOKEN",
            os.environ.get("HUGGINGFACE_HUB_TOKEN", ""),
        ),
        ("HUGGINGFACE_TOKEN", os.environ.get("HUGGINGFACE_TOKEN", "")),
        ("ORCHESTRATOR_CHECKPOINT_DIR", "/var/lib/discoverex/checkpoints"),
        ("NVIDIA_VISIBLE_DEVICES", "all"),
    )
    env = {key: value for key, value in env_pairs if value}
    return {
        "env": env,
        "working_dir": process_working_dir,
    }


def _is_process_work_pool(work_pool_name: str) -> bool:
    normalized = work_pool_name.strip().lower()
    return normalized.endswith("-process") or "process" in normalized


def _process_pull_steps(*, work_pool_name: str) -> list[dict[str, dict[str, str]]] | None:
    if not _is_process_work_pool(work_pool_name):
        return None
    working_dir = (
        os.environ.get("DISCOVEREX_DEPLOY_WORKING_DIR", "").strip() or "/app"
    )
    return [
        {
            "prefect.deployments.steps.set_working_directory": {
                "directory": working_dir,
            }
        }
    ]


def _update_process_deployment_pull_steps(
    deployment_id: str,
    *,
    work_pool_name: str,
) -> None:
    process_pull_steps = _process_pull_steps(work_pool_name=work_pool_name)
    if process_pull_steps is None:
        return
    with get_client(sync_client=True) as client:
        client.update_deployment(
            UUID(deployment_id),
            DeploymentUpdate(pull_steps=process_pull_steps),
        )


def _validate_required_worker_env() -> None:
    missing = [
        name
        for name in ("PREFECT_API_URL", "STORAGE_API_URL", "MLFLOW_TRACKING_URI")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(
            "worker deployment requires environment variables: "
            f"{missing_text}"
        )


def _deploy_embedded_flow(
    *,
    engine: str,
    flow_kind: str,
    purpose: str,
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
    deploy_kwargs: dict[str, Any] = {
        "name": deployment_name,
        "work_pool_name": work_pool_name,
        "work_queue_name": work_queue_name,
        "job_variables": _deployment_job_variables(work_pool_name=work_pool_name),
        "build": False,
        "push": False,
        "description": (
            f"Execute the {flow_kind} flow for purpose {purpose!r}."
            + (f" source_branch={branch!r}." if str(branch).strip() else "")
        ),
        "tags": [
            engine,
            flow_kind,
            f"purpose:{purpose}",
            *([f"branch:{branch}"] if str(branch).strip() else []),
        ],
        "version": deployment_version,
        "print_next_steps": False,
    }
    process_pull_steps = _process_pull_steps(work_pool_name=work_pool_name)
    if process_pull_steps is None:
        deploy_kwargs["image"] = image
    deployment_id = str(embedded_flow.deploy(**deploy_kwargs))
    if process_pull_steps is not None:
        _update_process_deployment_pull_steps(
            deployment_id,
            work_pool_name=work_pool_name,
        )
    return deployment_id


def main() -> int:
    args = _build_parser().parse_args()
    if not args.prefect_api_url:
        raise SystemExit("--prefect-api-url is required unless PREFECT_API_URL is set")
    deployment: DeploymentMetadata = _deployment_metadata(
        engine=args.engine,
        flow_kind=args.flow_kind,
        purpose=args.purpose,
        branch=args.branch,
        repo_url=args.repo_url,
        ref=_resolved_ref(args.branch, args.ref),
        flow_entrypoint=_resolved_entrypoint(args.flow_kind, args.flow_entrypoint),
        work_pool_name=args.work_pool_name,
        work_queue_name=(
            str(args.work_queue_name).strip()
            if str(args.work_queue_name or "").strip()
            else default_queue_for_purpose(
                args.purpose,
                default_queue=SETTINGS.prefect_work_queue,
            )
        ),
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
            purpose=args.purpose,
            branch=args.branch,
            flow_entrypoint=deployment["entrypoint"],
            work_pool_name=args.work_pool_name,
            work_queue_name=deployment["work_queue_name"],
            image=SETTINGS.prefect_work_image,
            deployment_version=args.deployment_version,
            deployment_name=deployment["deployment_name"],
            deployment_suffix=args.deployment_suffix,
        )
    print(json.dumps(deployment, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
