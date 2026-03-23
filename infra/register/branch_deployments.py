from __future__ import annotations

import re
from typing import Literal

try:
    from infra.register.settings import SETTINGS
except ModuleNotFoundError:
    from settings import SETTINGS  # type: ignore[import-not-found,no-redef]

FlowKind = Literal["generate", "verify", "animate", "combined"]
DeploymentPurpose = Literal["standard", "batch", "debug", "backfill"]
DEFAULT_FLOW_KIND: FlowKind = "combined"
SUPPORTED_FLOW_KINDS: tuple[FlowKind, ...] = (
    "generate",
    "verify",
    "animate",
    "combined",
)
SUPPORTED_DEPLOYMENT_PURPOSES: tuple[DeploymentPurpose, ...] = (
    "standard",
    "batch",
    "debug",
    "backfill",
)
FLOW_ENTRYPOINTS: dict[FlowKind, str] = {
    "generate": "prefect_flow.py:run_generate_job_flow",
    "verify": "prefect_flow.py:run_verify_job_flow",
    "animate": "prefect_flow.py:run_animate_job_flow",
    "combined": "prefect_flow.py:run_combined_job_flow",
}


def branch_slug(branch: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", branch.strip())
    cleaned = cleaned.strip("-").lower()
    if not cleaned:
        raise ValueError("branch must not be empty")
    return cleaned


def purpose_slug(purpose: str) -> str:
    cleaned = branch_slug(purpose)
    if cleaned not in SUPPORTED_DEPLOYMENT_PURPOSES:
        supported = ", ".join(SUPPORTED_DEPLOYMENT_PURPOSES)
        raise ValueError(
            f"unsupported purpose={purpose!r}; expected one of: {supported}"
        )
    return cleaned


def normalize_flow_kind(flow_kind: str) -> FlowKind:
    cleaned = str(flow_kind).strip().lower()
    if cleaned not in SUPPORTED_FLOW_KINDS:
        supported = ", ".join(SUPPORTED_FLOW_KINDS)
        raise ValueError(
            f"unsupported flow_kind={flow_kind!r}; expected one of: {supported}"
        )
    return cleaned  # type: ignore[return-value]


def deployment_name(
    *,
    engine: str,
    flow_kind: str,
    branch: str,
    suffix: str = "",
) -> str:
    normalized_flow_kind = normalize_flow_kind(flow_kind)
    parts = [engine.strip(), normalized_flow_kind, branch_slug(branch)]
    suffix_value = branch_slug(suffix) if str(suffix).strip() else ""
    if suffix_value:
        parts.append(suffix_value)
    return "-".join(parts)


def deployment_name_for_purpose(
    purpose: str,
    *,
    flow_kind: str = DEFAULT_FLOW_KIND,
    engine: str = SETTINGS.engine_name,
    suffix: str = "",
) -> str:
    normalized_flow_kind = normalize_flow_kind(flow_kind)
    parts = [engine.strip(), normalized_flow_kind, purpose_slug(purpose)]
    suffix_value = branch_slug(suffix) if str(suffix).strip() else ""
    if suffix_value:
        parts.append(suffix_value)
    return "-".join(parts)


def deployment_name_for_branch(
    branch: str,
    *,
    flow_kind: str = DEFAULT_FLOW_KIND,
    engine: str = SETTINGS.engine_name,
    suffix: str = "",
) -> str:
    return deployment_name(
        engine=engine,
        flow_kind=flow_kind,
        branch=branch,
        suffix=suffix,
    )


def experiment_deployment_name(
    purpose: str,
    *,
    experiment: str,
    engine: str = SETTINGS.engine_name,
) -> str:
    return "-".join(
        [
            engine.strip(),
            "generate",
            purpose_slug(purpose),
            branch_slug(experiment),
        ]
    )


def default_queue_for_purpose(purpose: str, *, default_queue: str = "gpu-fixed") -> str:
    normalized = purpose_slug(purpose)
    if normalized == "standard":
        return default_queue
    if normalized == "batch":
        return f"{default_queue}-batch"
    if normalized == "debug":
        return f"{default_queue}-debug"
    return f"{default_queue}-backfill"


def flow_entrypoint_for_kind(flow_kind: str) -> str:
    return FLOW_ENTRYPOINTS[normalize_flow_kind(flow_kind)]
