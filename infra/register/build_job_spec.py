#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from infra.register.register_orchestrator_job import (
    _build_job_spec,
    _build_parser,
    _resolved_job_name,
)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_JOB_SPEC_DIR = SCRIPT_DIR / "job_specs"


def _output_path(cli_value: str | None, job_name: str) -> Path:
    if cli_value:
        return Path(cli_value)
    return DEFAULT_JOB_SPEC_DIR / f"{job_name}.json"


def main() -> int:
    parser = _build_parser()
    parser.add_argument("--output-file", default=None)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    job_spec = _build_job_spec(args)
    if args.stdout:
        print(json.dumps(job_spec, ensure_ascii=True, indent=2))
        return 0
    output_path = _output_path(args.output_file, _resolved_job_name(args))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(job_spec, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
