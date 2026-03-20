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
    custom_header_keys: list[str]
    cf_access_configured: bool


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
        custom_header_keys=header_keys,
        cf_access_configured=bool(updated.get("CF_ACCESS_CLIENT_ID"))
        and bool(updated.get("CF_ACCESS_CLIENT_SECRET")),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Prefect client environment for embedded worker runtime."
    )
    parser.add_argument("command", choices=("shell", "summary"))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
