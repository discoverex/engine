from __future__ import annotations

from typing import Any

from discoverex.settings import AppSettings


def tracking_run_name(settings: AppSettings, default: str) -> str:
    return settings.execution.flow_run_id.strip() or default


def apply_tracking_identity(
    params: dict[str, Any],
    settings: AppSettings,
) -> dict[str, Any]:
    flow_run_id = settings.execution.flow_run_id.strip()
    flow_run_name = settings.execution.flow_run_name.strip()
    enriched = dict(params)
    if flow_run_id:
        enriched["prefect.flow_run_id"] = flow_run_id
    if flow_run_name:
        enriched["prefect.flow_run_name"] = flow_run_name
    return enriched
