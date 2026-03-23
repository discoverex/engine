#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import LogFilter, LogFilterFlowRunId
from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_CLIENT_CUSTOM_HEADERS,
    temporary_settings,
)

from infra.ops.register_orchestrator_job import _extra_headers
from infra.ops.settings import SETTINGS


async def check_status(flow_run_id_str: str) -> None:
    headers = _extra_headers()
    api_url = SETTINGS.prefect_api_url or "https://prefect-api.discoverex.qzz.io/api"

    flow_run_id = UUID(flow_run_id_str)

    with temporary_settings(
        updates={PREFECT_API_URL: api_url, PREFECT_CLIENT_CUSTOM_HEADERS: headers}
    ):
        async with get_client() as client:
            flow_run = await client.read_flow_run(flow_run_id)
            state = flow_run.state
            print(f"Status: {state.name if state is not None else 'UNKNOWN'}")
            print(f"Flow Run Name: {flow_run.name}")
            print(f"State Message: {state.message if state is not None else ''}")

            logs = await client.read_logs(
                log_filter=LogFilter(
                    flow_run_id=LogFilterFlowRunId(any_=[flow_run_id])
                ),
                limit=50,
            )
            print("\nRecent Logs:")
            for log in reversed(
                logs
            ):  # Logs are usually returned newest first? No, actually check.
                print(f"{log.timestamp} | {log.level} | {log.message}")


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    asyncio.run(check_status(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
