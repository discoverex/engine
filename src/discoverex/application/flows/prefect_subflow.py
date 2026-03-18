from __future__ import annotations

import json
from typing import Any

from prefect import flow

from .engine_entry import engine_entry_flow


@flow(name="discoverex-engine-entry-pipeline", persist_result=False)
def run_prefect_engine_entry_flow(
    command: str,
    args: dict[str, Any],
    config_name: str,
    config_dir: str = "conf",
    overrides: list[str] | None = None,
    resolved_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = engine_entry_flow(
        command=command,  # type: ignore[arg-type]
        args=args,
        config_name=config_name,
        config_dir=config_dir,
        overrides=overrides,
        resolved_config=resolved_config,
    )
    print(json.dumps(payload, ensure_ascii=True))
    return payload
