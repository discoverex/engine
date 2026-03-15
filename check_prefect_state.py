from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from prefect.client.orchestration import get_client
from prefect.settings import PREFECT_API_URL, PREFECT_CLIENT_CUSTOM_HEADERS, temporary_settings

# Add src to sys.path to import local modules
import sys
sys.path.append(str(Path.cwd()))

from infra.register.settings import SETTINGS

def _extra_headers() -> dict[str, str]:
    headers = {}
    cf_id = (SETTINGS.prefect_cf_access_client_id or SETTINGS.cf_access_client_id).strip()
    cf_secret = (SETTINGS.prefect_cf_access_client_secret or SETTINGS.cf_access_client_secret).strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers

async def check_state():
    api_url = SETTINGS.prefect_api_url or "https://prefect-api.discoverex.qzz.io/api"
    headers = _extra_headers()
    
    print(f"Checking Prefect API: {api_url}")
    print(f"CF Headers present: {'CF-Access-Client-Id' in headers}")

    updates = {
        PREFECT_API_URL: api_url,
        PREFECT_CLIENT_CUSTOM_HEADERS: json.dumps(headers)
    }

    with temporary_settings(updates=updates):
        async with get_client() as client:
            try:
                # 1. Check Work Pools
                pools = await client.read_work_pools()
                print("\nAvailable Work Pools:")
                for pool in pools:
                    print(f" - {pool.name} (type: {pool.type})")
                
                # 2. Check Recent Deployments
                deployments = await client.read_deployments(limit=10)
                print("\nRecent Deployments:")
                for d in deployments:
                    print(f" - {d.name} (pool: {d.work_pool_name})")
                    
            except Exception as e:
                print(f"\nError connecting to Prefect API: {e}")

if __name__ == "__main__":
    asyncio.run(check_state())
