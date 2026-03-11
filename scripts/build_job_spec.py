#!/usr/bin/env python3
from __future__ import annotations

import json

from register_orchestrator_job import _build_job_spec, _build_parser


def main() -> int:
    args = _build_parser().parse_args()
    job_spec = _build_job_spec(args)
    print(json.dumps(job_spec, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
