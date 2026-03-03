from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from discoverex.application.context import AppContextLike
from discoverex.application.use_cases.verify_only import run_verify_only


def run_replay_eval(scene_json_paths: list[Path | str], context: AppContextLike) -> Path:
    report_dir = context.artifacts_root / "reports"

    summary: list[dict[str, object]] = []
    for path in scene_json_paths:
        scene = context.scene_io.load_scene(path)
        before_total = scene.verification.final.total_score
        updated = run_verify_only(scene, context=context)
        after_total = updated.verification.final.total_score
        summary.append(
            {
                "scene_id": updated.meta.scene_id,
                "version_id": updated.meta.version_id,
                "status": updated.meta.status.value,
                "before_total_score": before_total,
                "after_total_score": after_total,
                "delta_total_score": after_total - before_total,
            }
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    report_path = context.report_writer.write_replay_eval_report(
        report_dir=report_dir,
        summary=summary,
        generated_at=datetime.now(timezone.utc).isoformat(),
        report_suffix=timestamp,
    )

    avg_after = (
        sum(float(item["after_total_score"]) for item in summary) / len(summary)
        if summary
        else 0.0
    )
    context.tracker.log_pipeline_run(
        run_name="replay_eval",
        params={"input_scene_count": len(scene_json_paths)},
        metrics={"avg_after_total_score": avg_after},
        artifacts=[report_path],
    )
    return report_path
