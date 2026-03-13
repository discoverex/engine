#!/usr/bin/env python3
import sys
import json
from pathlib import Path
from prefect.client.orchestration import get_client
from prefect.settings import PREFECT_API_URL, temporary_settings, PREFECT_CLIENT_CUSTOM_HEADERS
from prefect.client.schemas.filters import LogFilter, LogFilterFlowRunId
import asyncio

sys.path.append(str(Path(__file__).resolve().parent))
from settings import SETTINGS
from register_orchestrator_job import _extra_headers

async def check_status(flow_run_id_str: str):
    headers = _extra_headers()
    api_url = SETTINGS.prefect_api_url or "https://prefect-api.discoverex.qzz.io/api"
    from uuid import UUID
    flow_run_id = UUID(flow_run_id_str)
    
    with temporary_settings(updates={PREFECT_API_URL: api_url, PREFECT_CLIENT_CUSTOM_HEADERS: headers}):
        async with get_client() as client:
            flow_run = await client.read_flow_run(flow_run_id)
            print(f"Status: {flow_run.state.name}")
            print(f"Flow Run Name: {flow_run.name}")
            print(f"State Message: {flow_run.state.message}")
            
            logs = await client.read_logs(log_filter=LogFilter(flow_run_id=LogFilterFlowRunId(any_=[flow_run_id])), limit=50)
            print("\nRecent Logs:")
            for log in reversed(logs): # Logs are usually returned newest first? No, actually check.
                print(f"{log.timestamp} | {log.level} | {log.message}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    asyncio.run(check_status(sys.argv[1]))
