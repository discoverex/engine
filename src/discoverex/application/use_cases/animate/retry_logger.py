"""Validation stats logger — file recording + detailed terminal output.

Records each attempt to validation_stats.txt in the same format as
sprite_gen's _ValidationStats, enabling cross-system statistics.
"""

from __future__ import annotations

import logging
import re
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


_ATTEMPT_RE = re.compile(
    r"attempt\s+(\d+):\s*(\S+)\s*\|\s*([^[\]→]*?)"
    r"(?:\[AI:\s*([^\]]*)\])?"
    r"(?:\s*→\s*(\S+)\s*(?:\(([^)]*)\))?)?"
    r"(?:\s*\[VRAM:(\d+)MB\])?"
    r"\s*$"
)


def load_history(stats_file: Path, image_name: str | None = None) -> dict[str, Any]:
    """Parse validation_stats.txt and return attempt history."""
    result: dict[str, Any] = {"images": {}, "total_attempts": 0}
    if not stats_file.exists():
        return result
    try:
        lines = stats_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return result
    cur_img: str | None = None
    cur_attempts: list[dict[str, Any]] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("[") and "IMAGE:" in s:
            if cur_img and cur_attempts:
                result["images"][cur_img] = {"attempts": cur_attempts}
            cur_img = s.split("IMAGE:")[-1].strip()
            cur_attempts = []
            continue
        m = _ATTEMPT_RE.search(s)
        if m:
            issues_raw = m.group(3).strip().rstrip(",")
            issues = [x.strip() for x in issues_raw.split(",") if x.strip()]
            ai_raw = m.group(4)
            ai_issues = [x.strip() for x in ai_raw.split(",") if x.strip()] if ai_raw else []
            cur_attempts.append({"issues": issues, "ai_issues": ai_issues})
    if cur_img and cur_attempts:
        result["images"][cur_img] = {"attempts": cur_attempts}
    result["total_attempts"] = sum(len(v["attempts"]) for v in result["images"].values())
    if image_name and image_name in result["images"]:
        img = result["images"][image_name]
        return {"images": {image_name: img}, "total_attempts": len(img["attempts"])}
    return result


def build_history_negative(stats_file: Path, stem: str) -> str:
    """Build negative prompt from past failures (2+ occurrences)."""
    from .retry_state import ISSUE_NEGATIVE_MAP

    history = load_history(stats_file, stem)
    if history["total_attempts"] == 0:
        return ""
    ic: Counter[str] = Counter()
    for img_data in history["images"].values():
        for a in img_data["attempts"]:
            ic.update(a.get("issues", []))
            ic.update(a.get("ai_issues", []))
    negs = [ISSUE_NEGATIVE_MAP[k] for k, v in ic.most_common() if v >= 2 and ISSUE_NEGATIVE_MAP.get(k, "")]
    if negs:
        result = "，".join(negs)
        logger.info("  [이력 강화] 이전 %d회 실패 기반 negative: %s...", history["total_attempts"], result[:80])
        return result
    logger.info("  [이력] 이전 %d회 기록 (빈도 2회 이상 이슈 없음 → 스킵)", history["total_attempts"])
    return ""


def count_existing_videos(output_dir: Path, stem: str) -> int:
    """Count existing video files for this stem to avoid overwriting."""
    import glob
    patterns = [f"{stem}*_a*.mp4", f"{stem}*attempt*.mp4"]
    seen: set[str] = set()
    for pat in patterns:
        seen.update(glob.glob(str(output_dir / pat)))
    return len(seen)
