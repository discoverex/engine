#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import csv
import json
from html import escape
import os
from pathlib import Path
import subprocess
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

import boto3
from botocore.config import Config

from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import LogFilter, LogFilterFlowRunId
from prefect.settings import PREFECT_API_URL, PREFECT_CLIENT_CUSTOM_HEADERS, temporary_settings

from infra.ops.register_orchestrator_job import _extra_headers
from infra.ops.settings import SETTINGS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and aggregate object-generation quality sweep results."
    )
    parser.add_argument("--submitted-manifest", default=None)
    parser.add_argument("--sweep-id", default=None)
    parser.add_argument("--artifacts-root", default="/var/lib/discoverex/engine-runs")
    parser.add_argument("--env-file", default=str(Path(__file__).resolve().parents[1] / "worker" / ".env.fixed"))
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-csv", default=None)
    parser.add_argument("--output-html", default=None)
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must decode to an object")
    return payload


def _load_env_file(path: Path | None) -> None:
    if path is None or not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip("'").strip('"')
        os.environ[key] = value


def _public_object_base_url() -> str:
    explicit = os.environ.get("MINIO_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    storage_api = os.environ.get("STORAGE_API_URL", "").strip().rstrip("/")
    if storage_api:
        return f"{storage_api}/objects"
    return "https://storage-api.discoverex.qzz.io/objects"


def _cf_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    client_id = os.environ.get("CF_ACCESS_CLIENT_ID", "").strip()
    client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET", "").strip()
    if client_id and client_secret:
        headers["CF-Access-Client-Id"] = client_id
        headers["CF-Access-Client-Secret"] = client_secret
    return headers


def _artifact_api_base_url() -> str:
    storage_api = os.environ.get("STORAGE_API_URL", "").strip().rstrip("/")
    if not storage_api:
        storage_api = "https://storage-api.discoverex.qzz.io"
    return storage_api if storage_api.endswith("/artifact") else f"{storage_api}/artifact"


def _storage_api_base_url() -> str:
    storage_api = os.environ.get("STORAGE_API_URL", "").strip().rstrip("/")
    return storage_api or "https://storage-api.discoverex.qzz.io"


def _s3_uri_to_http_url(uri: str) -> str:
    raw = str(uri).strip()
    if not raw.startswith("s3://"):
        return raw
    remainder = raw.removeprefix("s3://")
    if "/" not in remainder:
        return ""
    bucket, key = remainder.split("/", 1)
    base = _public_object_base_url()
    return f"{base}/{quote(bucket, safe='')}/{quote(key, safe='/')}"


def _s3_client() -> Any:
    endpoint = (
        os.environ.get("MLFLOW_S3_ENDPOINT_URL", "").strip()
        or os.environ.get("S3_ENDPOINT_URL", "").strip()
        or os.environ.get("MINIO_ENDPOINT", "").strip()
    )
    if endpoint and not endpoint.startswith("http"):
        secure = os.environ.get("MINIO_SECURE", "false").strip().lower() == "true"
        scheme = "https" if secure else "http"
        endpoint = f"{scheme}://{endpoint}"
    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        aws_access_key_id=(
            os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
            or os.environ.get("MINIO_ACCESS_KEY", "").strip()
        ),
        aws_secret_access_key=(
            os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
            or os.environ.get("MINIO_SECRET_KEY", "").strip()
        ),
        region_name="us-east-1",
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=10,
            retries={"max_attempts": 2},
        ),
    )


def _fetch_json_s3_uri(uri: str) -> dict[str, Any] | None:
    raw = str(uri).strip()
    if not raw.startswith("s3://"):
        return None
    remainder = raw.removeprefix("s3://")
    if "/" not in remainder:
        return None
    bucket, key = remainder.split("/", 1)
    obj = _s3_client().get_object(Bucket=bucket, Key=key)
    payload = json.loads(obj["Body"].read().decode("utf-8", errors="replace"))
    return payload if isinstance(payload, dict) else None


def _fetch_json_url(url: str) -> dict[str, Any] | None:
    resolved = str(url).strip()
    if not resolved:
        return None
    payload = json.loads(_curl_text(url=resolved, method="GET"))
    return payload if isinstance(payload, dict) else None


def _http_json(method: str, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    parsed = json.loads(
        _curl_text(
            url=url,
            method=method,
            body=json.dumps(payload, ensure_ascii=True),
            content_type="application/json",
        )
    )
    return parsed if isinstance(parsed, dict) else None


def _curl_text(
    *,
    url: str,
    method: str,
    body: str | None = None,
    content_type: str | None = None,
) -> str:
    command = ["curl", "-fsS", "-X", method, url]
    if content_type:
        command.extend(["-H", f"Content-Type: {content_type}"])
    for key, value in _cf_headers().items():
        command.extend(["-H", f"{key}: {value}"])
    if body is not None:
        command.extend(["--data", body])
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _presign_get_url(
    *, object_uri: str, flow_run_id: str | None = None, attempt: int | None = None, filename: str | None = None
) -> str:
    _ = (flow_run_id, attempt, filename)
    errors: list[str] = []
    for url, payload in (
        (
            f"{_storage_api_base_url()}/artifacts/presign/get",
            {"object_uri": object_uri},
        ),
        (
            f"{_artifact_api_base_url()}/v1/presign/get",
            {
                "flow_run_id": flow_run_id or "",
                "attempt": attempt or 1,
                "kind": "custom",
                "filename": filename or "",
            },
        ),
    ):
        try:
            response = _http_json("POST", url, payload)
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue
        signed = str((response or {}).get("url", "")).strip()
        if signed:
            return signed
    if errors:
        raise RuntimeError("; ".join(errors))
    return ""


def _filename_from_object_uri(*, object_uri: str, flow_run_id: str, attempt: int) -> str:
    raw = str(object_uri).strip()
    prefix = f"s3://"
    if not raw.startswith(prefix):
        return ""
    remainder = raw.removeprefix(prefix)
    if "/" not in remainder:
        return ""
    _, key = remainder.split("/", 1)
    expected = f"jobs/{flow_run_id}/attempt-{attempt}/"
    if not key.startswith(expected):
        return ""
    return key.removeprefix(expected)


def _fetch_json_uri(uri: str) -> dict[str, Any] | None:
    raw = str(uri).strip()
    if not raw:
        return None
    if raw.startswith("s3://"):
        return _fetch_json_s3_uri(raw)
    return _fetch_json_url(raw)


async def _read_engine_summary(flow_run_id: str) -> dict[str, Any] | None:
    api_url = SETTINGS.prefect_api_url or "https://prefect-api.discoverex.qzz.io/api"
    flow_run_uuid = __import__("uuid").UUID(flow_run_id)
    updates = {
        PREFECT_API_URL: api_url,
        PREFECT_CLIENT_CUSTOM_HEADERS: _extra_headers(),
    }
    with temporary_settings(updates=updates):
        async with get_client() as client:
            logs = await client.read_logs(
                log_filter=LogFilter(
                    flow_run_id=LogFilterFlowRunId(any_=[flow_run_uuid])
                ),
                limit=120,
            )
    for log in logs:
        message = str(getattr(log, "message", "") or "")
        marker = "engine payload summary: "
        if marker not in message:
            continue
        try:
            summary = json.loads(message.split(marker, 1)[1])
        except json.JSONDecodeError:
            continue
        if isinstance(summary, dict):
            return summary
    return None


def _normalize_prefect_api_url() -> str:
    api_url = str(SETTINGS.prefect_api_url or os.environ.get("PREFECT_API_URL", "")).strip()
    if not api_url:
        api_url = "https://prefect-api.discoverex.qzz.io/api"
    return api_url if api_url.rstrip("/").endswith("/api") else f"{api_url.rstrip('/')}/api"


async def _read_flow_run_state(flow_run_id: str) -> dict[str, str]:
    flow_run_uuid = __import__("uuid").UUID(flow_run_id)
    updates = {
        PREFECT_API_URL: _normalize_prefect_api_url(),
        PREFECT_CLIENT_CUSTOM_HEADERS: _extra_headers(),
    }
    with temporary_settings(updates=updates):
        async with get_client() as client:
            flow_run = await client.read_flow_run(flow_run_uuid)
    state = getattr(flow_run, "state", None)
    return {
        "flow_run_name": str(getattr(flow_run, "name", "") or "").strip(),
        "prefect_state": str(getattr(state, "name", "") or "").strip(),
        "prefect_state_type": str(getattr(state, "type", "") or "").strip(),
        "prefect_state_message": str(getattr(state, "message", "") or "").strip(),
    }


def _recover_remote_cases(expected_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recovered: list[dict[str, Any]] = []
    for item in expected_results:
        flow_run_id = str(item.get("flow_run_id", "")).strip()
        policy_id = str(item.get("policy_id", "")).strip()
        scenario_id = str(item.get("scenario_id", "")).strip()
        if not flow_run_id or not policy_id or not scenario_id:
            continue
        try:
            summary = asyncio.run(_read_engine_summary(flow_run_id))
        except Exception:
            continue
        if not isinstance(summary, dict):
            continue
        manifest_uri = str(summary.get("engine_manifest_uri", "")).strip()
        attempt = int(str(summary.get("attempt", "1") or "1"))
        if not manifest_uri:
            continue
        try:
            manifest = None
            manifest_filename = _filename_from_object_uri(
                object_uri=manifest_uri,
                flow_run_id=flow_run_id,
                attempt=attempt,
            )
            if manifest_filename:
                manifest_url = _presign_get_url(
                    object_uri=manifest_uri,
                    flow_run_id=flow_run_id,
                    attempt=attempt,
                    filename=manifest_filename,
                )
                if manifest_url:
                    manifest = _fetch_json_url(manifest_url)
            if manifest is None:
                manifest = _fetch_json_uri(manifest_uri) or _fetch_json_url(
                    _s3_uri_to_http_url(manifest_uri)
                )
        except Exception:
            continue
        if not isinstance(manifest, dict):
            continue
        artifacts = manifest.get("artifacts", [])
        if not isinstance(artifacts, list):
            continue
        case_uri = ""
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            if str(artifact.get("logical_name", "")).strip() != "quality_case_json":
                continue
            case_uri = str(artifact.get("object_uri", "")).strip()
            if case_uri:
                break
        if not case_uri:
            continue
        try:
            case_payload = None
            case_filename = _filename_from_object_uri(
                object_uri=case_uri,
                flow_run_id=flow_run_id,
                attempt=attempt,
            )
            if case_filename:
                case_url = _presign_get_url(
                    object_uri=case_uri,
                    flow_run_id=flow_run_id,
                    attempt=attempt,
                    filename=case_filename,
                )
                if case_url:
                    case_payload = _fetch_json_url(case_url)
            if case_payload is None:
                case_payload = _fetch_json_uri(case_uri) or _fetch_json_url(
                    _s3_uri_to_http_url(case_uri)
                )
        except Exception:
            continue
        if not isinstance(case_payload, dict):
            continue
        case_payload["result_path"] = _s3_uri_to_http_url(case_uri)
        recovered.append(case_payload)
    return recovered


def _discover_cases(*, artifacts_root: Path, sweep_id: str) -> list[dict[str, Any]]:
    root = artifacts_root / "experiments" / "object_generation_sweeps" / sweep_id / "cases"
    if not root.exists():
        return []
    cases: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        payload = _load_json(path)
        payload["result_path"] = str(path)
        cases.append(payload)
    return cases


def _job_key(*, policy_id: str, scenario_id: str) -> str:
    return f"{policy_id}::{scenario_id}"


def _classify_missing_case(item: dict[str, Any], state: dict[str, str] | None) -> dict[str, Any]:
    record = {
        "job_name": str(item.get("job_name", "")).strip(),
        "policy_id": str(item.get("policy_id", "")).strip(),
        "scenario_id": str(item.get("scenario_id", "")).strip(),
        "flow_run_id": str(item.get("flow_run_id", "")).strip(),
        "deployment": str(item.get("deployment", "")).strip(),
        "flow_run_name": str((state or {}).get("flow_run_name", "")).strip(),
        "prefect_state": str((state or {}).get("prefect_state", "")).strip(),
        "prefect_state_type": str((state or {}).get("prefect_state_type", "")).strip(),
        "prefect_state_message": str((state or {}).get("prefect_state_message", "")).strip(),
    }
    if not bool(item.get("submitted")) or not record["flow_run_id"]:
        record["status"] = "not_submitted"
        return record
    state_name = record["prefect_state"].lower()
    state_type = record["prefect_state_type"].upper()
    if state_type == "COMPLETED" or state_name == "completed":
        record["status"] = "failed_to_collect"
        return record
    if state_type in {"FAILED", "CRASHED"} or state_name in {"failed", "crashed", "timedout"}:
        record["status"] = "failed"
        return record
    if state_type == "CANCELLED" or state_name in {"cancelled", "cancelling"}:
        record["status"] = "cancelled"
        return record
    if state_name in {"scheduled", "pending", "running", "late", "retrying"}:
        record["status"] = "pending"
        return record
    record["status"] = "failed_to_collect"
    return record


def _flow_run_states(expected_results: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    states: dict[str, dict[str, str]] = {}
    for item in expected_results:
        flow_run_id = str(item.get("flow_run_id", "")).strip()
        if not flow_run_id or flow_run_id in states:
            continue
        try:
            states[flow_run_id] = asyncio.run(_read_flow_run_state(flow_run_id))
        except Exception:
            states[flow_run_id] = {}
    return states


def _aggregate(
    cases: list[dict[str, Any]],
    *,
    submitted_manifest: dict[str, Any] | None = None,
    flow_run_states: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    expected_results = list((submitted_manifest or {}).get("results", []))
    expected_by_key: dict[str, dict[str, Any]] = {}
    for item in expected_results:
        policy_id = str(item.get("policy_id", "")).strip()
        scenario_id = str(item.get("scenario_id", "")).strip()
        if policy_id and scenario_id:
            expected_by_key[_job_key(policy_id=policy_id, scenario_id=scenario_id)] = item
    observed_keys = {
        _job_key(
            policy_id=str(case.get("policy_id", "")).strip(),
            scenario_id=str(case.get("scenario_id", "")).strip(),
        )
        for case in cases
        if str(case.get("policy_id", "")).strip() and str(case.get("scenario_id", "")).strip()
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        policy_id = str(case.get("policy_id", "")).strip() or "unknown"
        grouped.setdefault(policy_id, []).append(case)
    policies: list[dict[str, Any]] = []
    for policy_id, items in sorted(grouped.items()):
        run_scores = [
            float(summary.get("run_score"))
            for case in items
            if isinstance((quality := case.get("object_quality")), dict)
            and isinstance((summary := quality.get("summary")), dict)
            and isinstance(summary.get("run_score"), (int, float))
        ]
        mean_scores = [
            float(summary.get("mean_overall_score"))
            for case in items
            if isinstance((quality := case.get("object_quality")), dict)
            and isinstance((summary := quality.get("summary")), dict)
            and isinstance(summary.get("mean_overall_score"), (int, float))
        ]
        min_scores = [
            float(summary.get("min_overall_score"))
            for case in items
            if isinstance((quality := case.get("object_quality")), dict)
            and isinstance((summary := quality.get("summary")), dict)
            and isinstance(summary.get("min_overall_score"), (int, float))
        ]
        gallery = str(items[0].get("quality_gallery_ref", "")).strip() if items else ""
        policies.append(
            {
                "policy_id": policy_id,
                "case_count": len(items),
                "mean_run_score": round(sum(run_scores) / len(run_scores), 4) if run_scores else 0.0,
                "mean_object_score": round(sum(mean_scores) / len(mean_scores), 4) if mean_scores else 0.0,
                "min_object_score": round(min(min_scores), 4) if min_scores else 0.0,
                "gallery_ref": gallery,
                "cases": items,
            }
        )
    policies.sort(
        key=lambda item: (
            -float(item["mean_run_score"]),
            -float(item["mean_object_score"]),
            str(item["policy_id"]),
        )
    )
    missing_cases: list[dict[str, Any]] = []
    unsubmitted_cases: list[dict[str, Any]] = []
    failed_runs: list[dict[str, Any]] = []
    cancelled_runs: list[dict[str, Any]] = []
    pending_runs: list[dict[str, Any]] = []
    for key, item in sorted(expected_by_key.items()):
        if key in observed_keys:
            continue
        flow_run_id = str(item.get("flow_run_id", "")).strip()
        state = (flow_run_states or {}).get(flow_run_id) if flow_run_id else None
        record = _classify_missing_case(item, state)
        status = str(record.get("status", "")).strip()
        if status == "not_submitted":
            unsubmitted_cases.append(record)
        elif status == "pending":
            pending_runs.append(record)
        elif status == "failed":
            failed_runs.append(record)
        elif status == "cancelled":
            cancelled_runs.append(record)
        else:
            missing_cases.append(record)
    return {
        "policy_count": len(policies),
        "policies": policies,
        "missing_case_count": len(missing_cases),
        "missing_cases": missing_cases,
        "failed_run_count": len(failed_runs),
        "failed_runs": failed_runs,
        "cancelled_run_count": len(cancelled_runs),
        "cancelled_runs": cancelled_runs,
        "pending_run_count": len(pending_runs),
        "pending_runs": pending_runs,
        "not_submitted_count": len(unsubmitted_cases),
        "not_submitted_cases": unsubmitted_cases,
    }


def _write_csv(path: Path, policies: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "policy_id",
                "case_count",
                "mean_run_score",
                "mean_object_score",
                "min_object_score",
                "gallery_ref",
            ],
        )
        writer.writeheader()
        for item in policies:
            writer.writerow(
                {
                    "policy_id": item["policy_id"],
                    "case_count": item["case_count"],
                    "mean_run_score": item["mean_run_score"],
                    "mean_object_score": item["mean_object_score"],
                    "min_object_score": item["min_object_score"],
                    "gallery_ref": item["gallery_ref"],
                }
            )


def _write_html(path: Path, policies: list[dict[str, Any]]) -> None:
    lines = [
        "<html><head><meta charset='utf-8'><title>Object Quality Sweep</title></head><body>",
        "<h1>Object Quality Sweep</h1>",
        "<table border='1' cellspacing='0' cellpadding='6'>",
        "<tr><th>Policy</th><th>Run Score</th><th>Mean Object</th><th>Min Object</th><th>Gallery</th></tr>",
    ]
    for item in policies:
        gallery = str(item.get("gallery_ref", "")).strip()
        gallery_html = f"<a href='{escape(gallery)}'>gallery</a>" if gallery else ""
        lines.append(
            "<tr>"
            f"<td>{escape(str(item['policy_id']))}</td>"
            f"<td>{escape(str(item['mean_run_score']))}</td>"
            f"<td>{escape(str(item['mean_object_score']))}</td>"
            f"<td>{escape(str(item['min_object_score']))}</td>"
            f"<td>{gallery_html}</td>"
            "</tr>"
        )
    lines.append("</table></body></html>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = _build_parser().parse_args()
    env_file = Path(str(args.env_file)).resolve() if args.env_file else None
    _load_env_file(env_file)
    submitted_manifest = _load_json(Path(args.submitted_manifest).resolve()) if args.submitted_manifest else None
    sweep_id = str(args.sweep_id or (submitted_manifest or {}).get("sweep_id", "")).strip()
    if not sweep_id:
        raise SystemExit("sweep id is required via --sweep-id or --submitted-manifest")
    artifacts_root = Path(args.artifacts_root).resolve()
    cases = _discover_cases(artifacts_root=artifacts_root, sweep_id=sweep_id)
    if submitted_manifest is not None:
        cases.extend(_recover_remote_cases(list(submitted_manifest.get("results", []))))
        deduped: dict[str, dict[str, Any]] = {}
        for case in cases:
            policy_id = str(case.get("policy_id", "")).strip()
            scenario_id = str(case.get("scenario_id", "")).strip()
            if policy_id and scenario_id:
                deduped[_job_key(policy_id=policy_id, scenario_id=scenario_id)] = case
        cases = list(deduped.values())
    flow_run_states = _flow_run_states(list((submitted_manifest or {}).get("results", [])))
    aggregate = _aggregate(
        cases,
        submitted_manifest=submitted_manifest,
        flow_run_states=flow_run_states,
    )
    output = {
        "sweep_id": sweep_id,
        "artifacts_root": str(artifacts_root),
        "observed_case_count": len(cases),
        **aggregate,
    }
    json_path = Path(args.output_json).resolve() if args.output_json else Path.cwd() / f"{sweep_id}.collected.json"
    json_path.write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    csv_path = Path(args.output_csv).resolve() if args.output_csv else json_path.with_suffix(".csv")
    _write_csv(csv_path, output["policies"])
    html_path = Path(args.output_html).resolve() if args.output_html else json_path.with_suffix(".html")
    _write_html(html_path, output["policies"])
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
