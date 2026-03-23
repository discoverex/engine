from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shlex
from collections.abc import Mapping

DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)


@dataclasses.dataclass(frozen=True)
class WorkerStartupSummary:
    prefect_api_url: str
    prefect_work_pool: str
    prefect_work_queue: str
    checkpoint_dir: str
    mlflow_tracking_uri: str
    mlflow_s3_endpoint_url: str
    artifact_bucket: str
    metadata_db_url: str
    aws_access_key_id_present: bool
    aws_secret_access_key_present: bool
    custom_header_keys: list[str]
    cf_access_configured: bool


def _display_value(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if len(text) <= 12:
        return "***"
    return f"{text[:6]}...{text[-4:]}"


def build_prefect_client_headers(
    env: Mapping[str, str], default_user_agent: str = DEFAULT_BROWSER_USER_AGENT
) -> dict[str, str]:
    _ = default_user_agent
    headers: dict[str, str] = {}
    raw_headers = env.get("PREFECT_CLIENT_CUSTOM_HEADERS")
    if raw_headers:
        try:
            parsed = json.loads(raw_headers)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            headers = {str(key): str(value) for key, value in parsed.items()}
            headers.pop("User-Agent", None)

    cf_id = env.get("CF_ACCESS_CLIENT_ID")
    cf_secret = env.get("CF_ACCESS_CLIENT_SECRET")
    if cf_id and cf_secret:
        headers.setdefault("CF-Access-Client-Id", cf_id)
        headers.setdefault("CF-Access-Client-Secret", cf_secret)
    return headers


def apply_prefect_client_env(
    env: dict[str, str],
    *,
    default_queue: str | None = None,
    default_user_agent: str = DEFAULT_BROWSER_USER_AGENT,
) -> dict[str, str]:
    updated = env.copy()
    if default_queue:
        updated.setdefault("PREFECT_WORK_QUEUE", default_queue)
    headers = build_prefect_client_headers(updated, default_user_agent)
    if headers:
        updated["PREFECT_CLIENT_CUSTOM_HEADERS"] = json.dumps(
            headers, ensure_ascii=True
        )
    else:
        updated.pop("PREFECT_CLIENT_CUSTOM_HEADERS", None)
    return updated


def shell_exports(
    env: Mapping[str, str] | None = None,
    *,
    default_queue: str | None = None,
    default_user_agent: str = DEFAULT_BROWSER_USER_AGENT,
) -> str:
    base_env = dict(env or os.environ)
    updated = apply_prefect_client_env(
        base_env,
        default_queue=default_queue,
        default_user_agent=default_user_agent,
    )
    lines: list[str] = []
    queue = updated.get("PREFECT_WORK_QUEUE")
    if queue and base_env.get("PREFECT_WORK_QUEUE") != queue:
        lines.append(f"export PREFECT_WORK_QUEUE={shlex.quote(queue)}")
    header_value = updated.get("PREFECT_CLIENT_CUSTOM_HEADERS")
    if header_value:
        raw_headers = base_env.get("PREFECT_CLIENT_CUSTOM_HEADERS")
        if raw_headers != header_value:
            lines.append(
                f"export PREFECT_CLIENT_CUSTOM_HEADERS={shlex.quote(header_value)}"
            )
    elif base_env.get("PREFECT_CLIENT_CUSTOM_HEADERS"):
        lines.append("unset PREFECT_CLIENT_CUSTOM_HEADERS")
    return "\n".join(lines)


def startup_summary(
    env: Mapping[str, str] | None = None, *, default_queue: str | None = None
) -> WorkerStartupSummary:
    base_env = dict(env or os.environ)
    updated = apply_prefect_client_env(base_env, default_queue=default_queue)
    header_keys: list[str] = []
    raw_headers = updated.get("PREFECT_CLIENT_CUSTOM_HEADERS")
    if raw_headers:
        try:
            parsed = json.loads(raw_headers)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            header_keys = sorted(str(key) for key in parsed.keys())
    return WorkerStartupSummary(
        prefect_api_url=updated.get("PREFECT_API_URL", ""),
        prefect_work_pool=updated.get("PREFECT_WORK_POOL", ""),
        prefect_work_queue=updated.get("PREFECT_WORK_QUEUE", ""),
        checkpoint_dir=updated.get("ORCHESTRATOR_CHECKPOINT_DIR", ""),
        mlflow_tracking_uri=updated.get("MLFLOW_TRACKING_URI", ""),
        mlflow_s3_endpoint_url=updated.get("MLFLOW_S3_ENDPOINT_URL", ""),
        artifact_bucket=updated.get("ARTIFACT_BUCKET", ""),
        metadata_db_url=updated.get("METADATA_DB_URL", ""),
        aws_access_key_id_present=bool(updated.get("AWS_ACCESS_KEY_ID")),
        aws_secret_access_key_present=bool(updated.get("AWS_SECRET_ACCESS_KEY")),
        custom_header_keys=header_keys,
        cf_access_configured=bool(updated.get("CF_ACCESS_CLIENT_ID"))
        and bool(updated.get("CF_ACCESS_CLIENT_SECRET")),
    )


def startup_env_report(
    env: Mapping[str, str] | None = None, *, default_queue: str | None = None
) -> dict[str, object]:
    summary = startup_summary(env, default_queue=default_queue)
    return {
        "prefect_api_url": summary.prefect_api_url,
        "prefect_work_pool": summary.prefect_work_pool,
        "prefect_work_queue": summary.prefect_work_queue,
        "checkpoint_dir": summary.checkpoint_dir,
        "mlflow_tracking_uri": _display_value(summary.mlflow_tracking_uri),
        "mlflow_s3_endpoint_url": _display_value(summary.mlflow_s3_endpoint_url),
        "artifact_bucket": summary.artifact_bucket,
        "metadata_db_url": _display_value(summary.metadata_db_url),
        "aws_access_key_id": "set" if summary.aws_access_key_id_present else "unset",
        "aws_secret_access_key": (
            "set" if summary.aws_secret_access_key_present else "unset"
        ),
        "custom_header_keys": summary.custom_header_keys,
        "cf_access_configured": summary.cf_access_configured,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Prefect client environment for embedded worker runtime."
    )
    parser.add_argument("command", choices=("shell", "summary", "report"))
    parser.add_argument("--default-queue", default="")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "shell":
        exports = shell_exports(default_queue=args.default_queue or None)
        if exports:
            print(exports)
    if args.command == "summary":
        print(
            json.dumps(
                dataclasses.asdict(
                    startup_summary(default_queue=args.default_queue or None)
                ),
                ensure_ascii=True,
                sort_keys=True,
            )
        )
    if args.command == "report":
        print(
            json.dumps(
                startup_env_report(default_queue=args.default_queue or None),
                ensure_ascii=True,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
