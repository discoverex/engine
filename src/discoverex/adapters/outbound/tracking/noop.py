from __future__ import annotations

from pathlib import Path
from typing import Any


class NoOpTrackerAdapter:
    def __init__(self, **_: str) -> None:
        pass

    def log_pipeline_run(
        self,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, float],
        artifacts: list[Path],
    ) -> None:
        _ = (run_name, params, metrics, artifacts)
