from __future__ import annotations

import json
from typing import Any, cast
from urllib import request

from discoverex.settings import AppSettings

_USER_AGENT = "discoverex-engine-worker/1.0"


def storage_base_url(*, settings: AppSettings | dict[str, Any]) -> str:
    loaded = _coerce_settings(settings)
    raw = loaded.storage.storage_api_url.strip().rstrip("/")
    if not raw:
        raise RuntimeError("missing required storage_api_url in settings")
    return raw if raw.endswith("/artifact") else f"{raw}/artifact"


def http_json(
    method: str,
    url: str,
    payload: dict[str, object],
    *,
    settings: AppSettings | dict[str, Any],
) -> dict[str, Any] | list[dict[str, Any]]:
    loaded = _coerce_settings(settings)
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        url,
        method=method,
        data=body,
        headers=_gateway_headers(settings=loaded),
    )
    with request.urlopen(req) as resp:
        content_type = str(resp.headers.get("Content-Type", ""))
        text = resp.read().decode("utf-8", errors="replace")
    if not text.strip():
        raise RuntimeError(
            "storage API returned empty response body "
            f"url={url} content_type={content_type!r} "
            f"storage_api_url={_mask_value(loaded.storage.storage_api_url)}"
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "storage API returned non-JSON response "
            f"url={url} content_type={content_type!r} "
            f"storage_api_url={_mask_value(loaded.storage.storage_api_url)} "
            f"body_preview={text[:200]!r}"
        ) from exc
    if isinstance(parsed, dict):
        return cast(dict[str, Any], parsed)
    if isinstance(parsed, list):
        return [cast(dict[str, Any], row) for row in parsed if isinstance(row, dict)]
    raise RuntimeError(
        "unexpected storage API response type "
        f"url={url} content_type={content_type!r} "
        f"storage_api_url={_mask_value(loaded.storage.storage_api_url)} "
        f"response_type={type(parsed).__name__}"
    )


def upload_bytes(
    url: str,
    payload: bytes,
    *,
    settings: AppSettings | dict[str, Any],
) -> None:
    req = request.Request(
        url,
        method="PUT",
        data=payload,
        headers=_upload_headers(settings=settings),
    )
    with request.urlopen(req):
        return


def gateway_headers(*, settings: AppSettings | dict[str, Any]) -> dict[str, str]:
    return _gateway_headers(settings=_coerce_settings(settings))


def _gateway_headers(*, settings: AppSettings) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    cf_id = settings.worker_http.cf_access_client_id.strip()
    cf_secret = settings.worker_http.cf_access_client_secret.strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _upload_headers(*, settings: AppSettings | dict[str, Any]) -> dict[str, str]:
    headers = {
        "Content-Type": "application/octet-stream",
        "User-Agent": _USER_AGENT,
    }
    loaded = _coerce_settings(settings)
    cf_id = loaded.worker_http.cf_access_client_id.strip()
    cf_secret = loaded.worker_http.cf_access_client_secret.strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _coerce_settings(settings: AppSettings | dict[str, Any]) -> AppSettings:
    if isinstance(settings, AppSettings):
        return settings
    return AppSettings.model_validate(settings)


def _mask_value(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if len(text) <= 12:
        return "***"
    return f"{text[:8]}...{text[-4:]}"
