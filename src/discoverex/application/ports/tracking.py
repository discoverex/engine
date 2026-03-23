from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class TrackerPort(Protocol):
    def log_pipeline_run(
        self,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, float],
        artifacts: list[Path],
        tags: dict[str, str] | None = None,
    ) -> str | None: ...
