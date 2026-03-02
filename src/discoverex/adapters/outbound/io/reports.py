from __future__ import annotations

import json
from pathlib import Path

from discoverex.domain.scene import Scene


class JsonReportWriterAdapter:
    def __init__(self, **_: str) -> None:
        pass

    def write_verification_report(self, saved_dir: Path, scene: Scene) -> Path:
        report_path = saved_dir / "verification.json"
        payload = {
            "scene_id": scene.meta.scene_id,
            "version_id": scene.meta.version_id,
            "status": scene.meta.status.value,
            "verification": scene.verification.model_dump(mode="json", by_alias=True),
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report_path

    def write_replay_eval_report(
        self,
        report_dir: Path,
        summary: list[dict[str, object]],
        generated_at: str,
        report_suffix: str,
    ) -> Path:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"replay_eval_{report_suffix}.json"
        report_path.write_text(
            json.dumps(
                {
                    "generated_at": generated_at,
                    "count": len(summary),
                    "results": summary,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return report_path

