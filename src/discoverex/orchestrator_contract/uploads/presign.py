from __future__ import annotations

from typing import Any

from ..storage_http import http_json, storage_base_url
from discoverex.settings import AppSettings


def prepare_links(
    *,
    flow_run_id: str,
    attempt: int,
    entries: tuple[str, ...],
    settings: AppSettings | dict[str, Any],
) -> list[dict[str, Any]]:
    rows = http_json(
        "POST",
        f"{storage_base_url(settings=settings)}/v1/presign/batch",
        {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "entries": [
                {
                    "flow_run_id": flow_run_id,
                    "attempt": attempt,
                    "kind": kind,
                    "filename": output_filename(kind),
                }
                for kind in entries
            ],
        },
        settings=settings,
    )
    if not isinstance(rows, list):
        raise RuntimeError("unexpected storage API batch response")
    return rows


def prepare_custom_links(
    *,
    flow_run_id: str,
    attempt: int,
    filenames: list[str],
    settings: AppSettings | dict[str, Any],
) -> list[dict[str, Any]]:
    rows = http_json(
        "POST",
        f"{storage_base_url(settings=settings)}/v1/presign/batch",
        {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "entries": [
                {
                    "flow_run_id": flow_run_id,
                    "attempt": attempt,
                    "kind": "custom",
                    "filename": filename,
                }
                for filename in filenames
            ],
        },
        settings=settings,
    )
    if not isinstance(rows, list):
        raise RuntimeError("unexpected storage API custom batch response")
    return rows


def put_custom_link(
    *,
    flow_run_id: str,
    attempt: int,
    filename: str,
    settings: AppSettings | dict[str, Any],
) -> dict[str, Any]:
    row = http_json(
        "POST",
        f"{storage_base_url(settings=settings)}/v1/presign/put",
        {
            "flow_run_id": flow_run_id,
            "attempt": attempt,
            "kind": "custom",
            "filename": filename,
        },
        settings=settings,
    )
    if not isinstance(row, dict):
        raise RuntimeError("unexpected storage API put response")
    return row


def output_filename(kind: str) -> str:
    if kind in {"stdout", "stderr"}:
        return f"{kind}.log"
    if kind == "manifest":
        return "artifacts.json"
    return f"{kind}.json"
