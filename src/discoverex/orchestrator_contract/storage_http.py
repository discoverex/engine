from __future__ import annotations

import json
import os
from typing import Any, cast
from urllib import request

_USER_AGENT = "discoverex-engine-worker/1.0"


def storage_base_url() -> str:
    raw = os.getenv("STORAGE_API_URL", "").strip().rstrip("/")
    if not raw:
        raise RuntimeError("missing required environment variable: STORAGE_API_URL")
    return raw if raw.endswith("/artifact") else f"{raw}/artifact"


def http_json(
    method: str,
    url: str,
    payload: dict[str, object],
) -> dict[str, Any] | list[dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(url, method=method, data=body, headers=_gateway_headers())
    with request.urlopen(req) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return cast(dict[str, Any], parsed)
    if isinstance(parsed, list):
        return [cast(dict[str, Any], row) for row in parsed if isinstance(row, dict)]
    raise RuntimeError("unexpected storage API response type")


def upload_bytes(url: str, payload: bytes) -> None:
    req = request.Request(
        url,
        method="PUT",
        data=payload,
        headers=_upload_headers(),
    )
    with request.urlopen(req):
        return


def _gateway_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _upload_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/octet-stream",
        "User-Agent": _USER_AGENT,
    }
    cf_id = os.getenv("CF_ACCESS_CLIENT_ID", "").strip()
    cf_secret = os.getenv("CF_ACCESS_CLIENT_SECRET", "").strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers
