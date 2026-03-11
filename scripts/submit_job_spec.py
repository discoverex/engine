#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from register_orchestrator_job import submit_job_spec


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit an existing job spec JSON to a Prefect deployment."
    )
    parser.add_argument("--prefect-api-url", default=os.getenv("PREFECT_API_URL", ""))
    parser.add_argument("--deployment", default=os.getenv("PREFECT_DEPLOYMENT", ""))
    parser.add_argument("--job-spec-file", default=None)
    parser.add_argument("--job-spec-json", default=None)
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--resume-key", default=None)
    parser.add_argument("--checkpoint-dir", default=None)
    return parser


def _load_job_spec(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.job_spec_file) == bool(args.job_spec_json):
        raise SystemExit("provide exactly one of --job-spec-file or --job-spec-json")
    if args.job_spec_file:
        raw = Path(args.job_spec_file).read_text(encoding="utf-8")
    else:
        raw = str(args.job_spec_json)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid job spec JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("job spec must decode to a JSON object")
    return payload


def main() -> int:
    args = _build_parser().parse_args()
    output = submit_job_spec(
        job_spec=_load_job_spec(args),
        prefect_api_url=args.prefect_api_url,
        deployment=args.deployment,
        job_name=args.job_name,
        resume_key=args.resume_key,
        checkpoint_dir=args.checkpoint_dir,
    )
    print(json.dumps(output, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
