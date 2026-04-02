from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from infra.prefect.bootstrap import repo_root
from infra.prefect.job_spec import string_value
from infra.prefect.runtime import summarize_run_request


def log_start_summary(
    *,
    logger: Any,
    job_spec: dict[str, Any],
    payload: dict[str, Any],
    env: dict[str, str],
    resume_key: str | None,
    checkpoint_dir: str | None,
    outputs_prefix: str,
) -> None:
    summary = summarize_run_request(
        job_spec=job_spec,
        payload=payload,
        env=env,
        resume_key=resume_key,
        checkpoint_dir=checkpoint_dir,
        outputs_prefix=outputs_prefix,
    )
    logger.info(
        "engine flow start: %s",
        json.dumps(summary, ensure_ascii=True, sort_keys=True),
    )
    print(
        "[discoverex-engine-flow] start "
        + json.dumps(summary, ensure_ascii=True, sort_keys=True),
        file=sys.stderr,
    )


def log_failure_summary(
    *,
    logger: Any,
    flow_run_id: str,
    attempt: int,
    resume_key: str | None,
    checkpoint_dir: str | None,
) -> None:
    failure_summary = {
        "repo_root": str(repo_root()),
        "python_executable": sys.executable,
        "resume_key": string_value(resume_key),
        "checkpoint_dir": string_value(checkpoint_dir),
        "flow_run_id": flow_run_id,
        "attempt": attempt,
    }
    logger.error(
        "engine flow failed before completion: %s",
        json.dumps(failure_summary, ensure_ascii=True, sort_keys=True),
    )
    print(
        "[discoverex-engine-flow] failure-context "
        + json.dumps(failure_summary, ensure_ascii=True, sort_keys=True),
        file=sys.stderr,
    )
    print(traceback.format_exc(), file=sys.stderr, end="")
