from __future__ import annotations

import json
import os
import sys

from discoverex.runtime_logging import configure_logging

from .run_engine_job import run_engine_job

INPUTS_ENV = "ORCH_JOB_INPUTS_JSON"


def _load_payload() -> str:
    raw = os.getenv(INPUTS_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"missing required env: {INPUTS_ENV}")
    return raw


def main() -> None:
    configure_logging()
    try:
        payload = run_engine_job(_load_payload())
    except Exception as exc:
        print(f"[discoverex-engine-entry] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
