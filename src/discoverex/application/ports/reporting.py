from __future__ import annotations

from pathlib import Path
from typing import Protocol

from discoverex.domain.scene import Scene


class ReportWriterPort(Protocol):
    def write_verification_report(self, saved_dir: Path, scene: Scene) -> Path: ...

    def write_replay_eval_report(
        self,
        report_dir: Path,
        summary: list[dict[str, object]],
        generated_at: str,
        report_suffix: str,
    ) -> Path: ...
