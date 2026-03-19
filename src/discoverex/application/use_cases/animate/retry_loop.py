"""Retry loop for WAN I2V animation generation."""
from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from discoverex.domain.animate import (
    AIValidationContext,
    AIValidationFix,
    AnimationGenerationParams,
    AnimationValidation,
    AnimationValidationThresholds,
    VisionAnalysis,
)

from .retry_logger import RetryLogger, count_existing_videos
from .retry_state import (
    CONSECUTIVE_FAIL_THRESHOLD,
    MOTION_ONLY_ISSUES,
    QUALITY_ISSUES,
    SOFT_ISSUES,
    LoopState,
)

logger = logging.getLogger(__name__)

@dataclass
class RetryConfig:
    max_retries: int = 7
    initial_scale: float = 0.65
    thresholds: AnimationValidationThresholds = field(default_factory=AnimationValidationThresholds)

@dataclass
class RetryResult:
    success: bool
    video_path: Path | None = None
    analysis: VisionAnalysis | None = None
    attempts: int = 0
    seed: int = 0

class RetryLoop:
    """Generation + validation retry loop with AI feedback."""

    def __init__(
        self, config: RetryConfig,
        animation_generator: Any, numerical_validator: Any,
        ai_validator: Any, vision_analyzer: Any, mask_generator: Any,
    ) -> None:
        self._cfg = config
        self._gen = animation_generator
        self._num_val = numerical_validator
        self._ai_val = ai_validator
        self._vision = vision_analyzer
        self._mask = mask_generator
        self._issue_counter: Counter[str] = Counter()

    def run(
        self, image_path: Path, analysis: VisionAnalysis,
        mask_path: Path | None, output_dir: Path,
    ) -> RetryResult:
        state = LoopState(analysis=analysis, mask_path=mask_path)
        stem = image_path.stem
        stats_file = output_dir / "validation_stats.txt"
        self._log = RetryLogger(stats_file, stem)
        self._log.start_image()
        offset = count_existing_videos(output_dir, stem)
        if offset:
            logger.info("  [이력] 기존 영상 %d개 발견 → attempt %d부터 시작", offset, offset + 1)
        for attempt in range(1, self._cfg.max_retries + 1):
            seed = random.randint(0, 2**32 - 1)
            actual = attempt + offset
            video = self._try_generate(image_path, state, seed, stem, actual, output_dir)
            if video is None:
                continue
            val = self._num_val.validate(video, state.analysis, self._cfg.thresholds)
            if val.passed:
                r = self._on_pass(video, image_path, state, attempt, seed, val)
                if r is not None:
                    self._log.finish_image()
                    return r
            else:
                self._on_fail(video, image_path, state, val, attempt, seed)
        self._log.finish_image()
        return RetryResult(success=False, analysis=state.analysis, attempts=self._cfg.max_retries)

    def _try_generate(
        self, image: Path, s: LoopState, seed: int,
        stem: str, attempt: int, out: Path,
    ) -> Path | None:
        pos, neg = s.build_prompts()
        params = AnimationGenerationParams(
            positive=pos, negative=neg,
            frame_rate=s.current_fps, frame_count=s.analysis.frame_count,
            seed=seed, output_dir=str(out), stem=stem, attempt=attempt,
            pingpong=s.analysis.pingpong,
        )
        try:
            result = self._gen.generate(None, str(image), params)
            return Path(result.video_path)
        except Exception as e:
            logger.warning(f"[Retry] generation failed: {e}")
            return None

    def _on_pass(
        self, video: Path, image: Path, s: LoopState,
        attempt: int, seed: int, val: AnimationValidation,
    ) -> RetryResult | None:
        ctx = AIValidationContext(
            current_fps=s.current_fps, current_scale=s.current_scale,
            positive=s.build_prompts()[0], negative=s.build_prompts()[1],
        )
        ai = self._ai_val.validate(video, image, ctx)
        if not ai.passed and ai.issues:
            hard = [i for i in ai.issues if i not in SOFT_ISSUES]
            if not hard:
                ai = AIValidationFix(passed=True, issues=ai.issues, reason="soft_pass")
        if ai.passed:
            self._log.log_attempt(attempt, seed, s.current_fps, val, ai, success=True)
            return RetryResult(success=True, video_path=video, analysis=s.analysis, attempts=attempt, seed=seed)
        self._record_issues(ai.issues)
        remedy, detail = self._resolve_remedy(ai, image, s)
        self._log.log_attempt(attempt, seed, s.current_fps, val, ai, remedy, detail)
        return None

    def _on_fail(
        self, video: Path, image: Path, s: LoopState,
        val: AnimationValidation, attempt: int, seed: int,
    ) -> None:
        self._record_issues(val.failed_checks)
        if set(val.failed_checks) <= MOTION_ONLY_ISSUES:
            s.consecutive_nomotion += 1
            if attempt == 1 or s.consecutive_nomotion < CONSECUTIVE_FAIL_THRESHOLD:
                self._log.log_attempt(attempt, seed, s.current_fps, val, remedy="seed_retry")
                return
            s.consecutive_nomotion = 0
            self._switch_action(image, s)
            self._log.log_attempt(attempt, seed, s.current_fps, val, remedy="action_switch", remedy_detail=s.analysis.action_desc)
            return
        s.consecutive_nomotion = 0
        ctx = AIValidationContext(
            current_fps=s.current_fps, current_scale=s.current_scale,
            positive=s.build_prompts()[0], negative=s.build_prompts()[1],
        )
        ai = self._ai_val.validate(video, image, ctx)
        self._record_issues(ai.issues)
        remedy, detail = self._resolve_remedy(ai, image, s)
        self._log.log_attempt(attempt, seed, s.current_fps, val, ai, remedy, detail)

    def _resolve_remedy(
        self, ai: AIValidationFix, image: Path, s: LoopState,
    ) -> tuple[str, str]:
        if self._should_switch(ai.issues, s):
            self._switch_action(image, s)
            return "action_switch", s.analysis.action_desc
        self._apply_adj(ai, s)
        self._log.log_ai_adjust(ai)
        return "ai_adjust", ""

    def _switch_action(self, image: Path, s: LoopState) -> None:
        try:
            new = self._vision.analyze_with_exclusion(image, s.analysis.action_desc)
            s.analysis = new
            s.current_fps = new.frame_rate
            s.rebuild_base_prompts()
            self._log.log_action_switch(new.action_desc)
            s.adj_positive = ""
            s.adj_negative = ""
            if s.mask_path:
                try:
                    s.mask_path = self._mask.generate(image, new.moving_zone)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[ActionSwitch] failed: {e}")

    def _apply_adj(self, ai: AIValidationFix, s: LoopState) -> None:
        if ai.frame_rate is not None:
            s.current_fps = ai.frame_rate
        if ai.scale is not None:
            s.current_scale = ai.scale
        if ai.positive:
            s.adj_positive = ai.positive
        if ai.negative:
            s.adj_negative = ai.negative

    def _should_switch(self, issues: list[str], s: LoopState) -> bool:
        if issues and set(issues) & QUALITY_ISSUES:
            s.consecutive_quality += 1
            if s.consecutive_quality >= CONSECUTIVE_FAIL_THRESHOLD:
                s.consecutive_quality = 0
                return True
        else:
            s.consecutive_quality = 0
        return False

    def _record_issues(self, issues: list[str]) -> None: self._issue_counter.update(issues)