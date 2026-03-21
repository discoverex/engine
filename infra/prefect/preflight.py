from __future__ import annotations

import json
from typing import Any
from urllib import request
from urllib.parse import urlsplit

from discoverex.settings import AppSettings, build_settings


def validate_runtime_services(
    *,
    payload: dict[str, Any],
    env: dict[str, str],
    logger: Any,
) -> None:
    settings = _build_payload_settings(payload=payload, env=env)
    _validate_mlflow(settings=settings, logger=logger)
    _validate_storage(settings=settings, logger=logger)


def _build_payload_settings(*, payload: dict[str, Any], env: dict[str, str]) -> AppSettings:
    resolved = payload.get("resolved_settings")
    if resolved is None:
        resolved = payload.get("resolved_config")
    return build_settings(
        config_name=str(payload.get("config_name") or "generate"),
        config_dir=str(payload.get("config_dir") or "conf"),
        overrides=_coerce_overrides(payload.get("overrides")),
        resolved_config=resolved,
        env=env,
    )


def _validate_mlflow(*, settings: AppSettings, logger: Any) -> None:
    tracking_uri = settings.tracking.uri.strip()
    if not tracking_uri:
        return
    if urlsplit(tracking_uri).scheme.lower() not in {"http", "https"}:
        return
    health_url = f"{tracking_uri.rstrip('/')}/health"
    logger.info("preflight mlflow healthcheck url=%s", health_url)
    req = request.Request(health_url, method="GET", headers=_http_headers(settings))
    try:
        with request.urlopen(req, timeout=20) as resp:
            if int(getattr(resp, "status", 200) or 200) >= 400:
                raise RuntimeError(f"unexpected status={getattr(resp, 'status', '')}")
    except Exception as exc:
        raise RuntimeError(
            f"mlflow preflight failed tracking_uri={tracking_uri} health_url={health_url}: {exc}"
        ) from exc


def _validate_storage(*, settings: AppSettings, logger: Any) -> None:
    storage_api_url = settings.storage.storage_api_url.strip()
    if not storage_api_url:
        return
    base_url = storage_api_url.rstrip("/")
    if not base_url.endswith("/artifact"):
        base_url = f"{base_url}/artifact"
    url = f"{base_url}/v1/presign/batch"
    logger.info("preflight storage probe url=%s", url)
    probe_attempt = 1
    body = json.dumps(
        {
            "flow_run_id": settings.execution.flow_run_id or "preflight",
            "attempt": probe_attempt,
            "entries": [
                {
                    "flow_run_id": settings.execution.flow_run_id or "preflight",
                    "attempt": probe_attempt,
                    "kind": "stdout",
                    "filename": "__preflight__.log",
                }
            ],
        },
        ensure_ascii=True,
    ).encode("utf-8")
    req = request.Request(
        url,
        method="POST",
        data=body,
        headers={
            **_http_headers(settings),
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(
            f"storage preflight failed storage_api_url={storage_api_url} probe_url={url}: {exc}"
        ) from exc
    if not text.strip():
        raise RuntimeError(
            f"storage preflight failed storage_api_url={storage_api_url} probe_url={url}: empty response"
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "storage preflight failed "
            f"storage_api_url={storage_api_url} probe_url={url}: non-json response {text[:200]!r}"
        ) from exc
    if not isinstance(parsed, list):
        raise RuntimeError(
            "storage preflight failed "
            f"storage_api_url={storage_api_url} probe_url={url}: unexpected response type {type(parsed).__name__}"
        )


def _http_headers(settings: AppSettings) -> dict[str, str]:
    headers = {"User-Agent": "discoverex-prefect-preflight/1.0"}
    cf_id = settings.worker_http.cf_access_client_id.strip()
    cf_secret = settings.worker_http.cf_access_client_secret.strip()
    if cf_id and cf_secret:
        headers["CF-Access-Client-Id"] = cf_id
        headers["CF-Access-Client-Secret"] = cf_secret
    return headers


def _coerce_overrides(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]
