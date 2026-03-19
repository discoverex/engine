"""Validation stats logger — file recording + detailed terminal output.

Records each attempt to validation_stats.txt in the same format as
sprite_gen's _ValidationStats, enabling cross-system statistics.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from discoverex.domain.animate import AIValidationFix, AnimationValidation

logger = logging.getLogger(__name__)


class RetryLogger:
    """Logs retry attempts to terminal + validation_stats.txt."""

    def __init__(self, stats_file: Path, stem: str) -> None:
        self._stats_file = stats_file
        self._stem = stem
        self._records: list[dict[str, Any]] = []
        self._metric_items: Counter[str] = Counter()
        self._ai_items: Counter[str] = Counter()
        self._remedies: Counter[str] = Counter()

    def start_image(self) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # noqa: DTZ005
        self._append(f"\n[{ts}] IMAGE: {self._stem}\n")

    def log_attempt(
        self, attempt: int, seed: int, fps: int,
        val: AnimationValidation | None = None,
        ai: AIValidationFix | None = None,
        remedy: str = "", remedy_detail: str = "",
        success: bool = False,
    ) -> None:
        # Terminal log
        logger.info(
            "  [시도 %d] seed=%d fps=%d", attempt, seed, fps,
        )

        # Build stats line
        if success:
            result = "success"
            metrics = ""
        elif val and not val.passed:
            result = "metric_fail"
            metrics = ", ".join(val.failed_checks)
            self._metric_items.update(val.failed_checks)
        else:
            result = "unknown"
            metrics = ""

        ai_str = ""
        if ai and ai.issues:
            ai_str = f" [AI: {', '.join(ai.issues)}]"
            self._ai_items.update(ai.issues)

        remedy_str = ""
        if remedy:
            self._remedies[remedy] += 1
            detail = f" ({remedy_detail})" if remedy_detail else ""
            remedy_str = f" → {remedy}{detail}"

        line = f"  attempt {attempt}: {result:<12} | {metrics:<40}{ai_str}{remedy_str}\n"
        self._append(line)

        # Detailed terminal log
        if val and not val.passed:
            logger.info("  ❌ 수치 검증 실패: %s", val.failed_checks)
            if val.scores:
                logger.info("     scores: %s", val.scores)
        if ai and not ai.passed:
            logger.info("  ❌ AI 검증 실패: %s | %s", ai.issues, ai.reason)
        if success:
            logger.info("  ✅ 성공 (attempt %d, seed=%d)", attempt, seed)

    def log_action_switch(self, new_action: str) -> None:
        logger.info("  ⚠ 액션 전환: %s", new_action)

    def log_ai_adjust(self, ai: AIValidationFix) -> None:
        parts = []
        if ai.frame_rate is not None:
            parts.append(f"fps→{ai.frame_rate}")
        if ai.positive:
            parts.append(f"pos:{ai.positive[:30]}")
        if ai.negative:
            parts.append(f"neg:{ai.negative[:30]}")
        if parts:
            logger.info("  [AI조정] %s", ", ".join(parts))

    def finish_image(self) -> None:
        self._append("  ---\n")
        total = len(self._records)
        if total == 0:
            return
        logger.info(
            "────── [통계] %s — 총 %d회 시도 ──────", self._stem, total,
        )
        if self._metric_items:
            logger.info("  수치실패: %s", dict(self._metric_items))
        if self._ai_items:
            logger.info("  AI이슈: %s", dict(self._ai_items))
        if self._remedies:
            logger.info("  보완조치: %s", dict(self._remedies))

    def record(self, attempt_data: dict[str, Any]) -> None:
        self._records.append(attempt_data)

    def _append(self, text: str) -> None:
        try:
            self._stats_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._stats_file, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            logger.warning("[Stats] write failed: %s", e)


def count_existing_videos(output_dir: Path, stem: str) -> int:
    """Count existing video files for this stem to avoid overwriting."""
    import glob
    patterns = [f"{stem}*_a*.mp4", f"{stem}*attempt*.mp4"]
    seen: set[str] = set()
    for pat in patterns:
        seen.update(glob.glob(str(output_dir / pat)))
    return len(seen)
