"""AnimateOrchestrator — 5-stage sprite animation pipeline coordinator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from discoverex.domain.animate import (
    ModeClassification,
    ProcessingMode,
    VisionAnalysis,
)
from discoverex.domain.animate_keyframe import (
    ConvertedAsset,
    KeyframeAnimation,
    KeyframeConfig,
    TransparentSequence,
)

from .retry_loop import RetryConfig, RetryLoop

logger = logging.getLogger(__name__)


@dataclass
class AnimateResult:
    """Final result of the animate pipeline."""

    success: bool
    mode: ModeClassification | None = None
    video_path: Path | None = None
    analysis: VisionAnalysis | None = None
    attempts: int = 0
    seed: int = 0
    keyframe_config: KeyframeAnimation | None = None
    transparent: TransparentSequence | None = None
    converted: ConvertedAsset | None = None


@dataclass
class AnimateOrchestrator:
    """Coordinates the full animate pipeline using port interfaces."""

    mode_classifier: Any
    vision_analyzer: Any
    animation_generator: Any
    numerical_validator: Any
    ai_validator: Any
    post_motion_classifier: Any
    bg_remover: Any
    mask_generator: Any
    keyframe_generator: Any
    format_converter: Any
    output_dir: Path = field(default_factory=lambda: Path("artifacts/animate"))
    max_retries: int = 7

    def run(self, image_path: Path) -> AnimateResult:
        stem = image_path.stem
        logger.info(f"[Animate] start: {stem}")

        # Stage 1: Mode classification
        mode = self.mode_classifier.classify(image_path)
        logger.info(
            "[Stage1] mode=%s facing=%s scene=%s deformable=%s action=%s",
            mode.processing_mode.value, mode.facing_direction.value,
            mode.is_scene, mode.has_deformable, mode.suggested_action)
        if mode.subject_desc or mode.reason:
            logger.info("  → 대상: %s | 근거: %s", mode.subject_desc, mode.reason[:80] if mode.reason else "")

        if mode.processing_mode == ProcessingMode.KEYFRAME_ONLY:
            return self._handle_keyframe_only(mode)

        # MOTION_NEEDED path
        return self._handle_motion_needed(image_path, mode)

    def _handle_keyframe_only(self, mode: ModeClassification) -> AnimateResult:
        config = KeyframeConfig(
            suggested_action=mode.suggested_action,
            facing_direction=mode.facing_direction.value,
        )
        kf = self.keyframe_generator.generate(config)
        logger.info(f"[Animate] KEYFRAME_ONLY -> {kf.animation_type}")
        return AnimateResult(success=True, mode=mode, keyframe_config=kf)

    def _handle_motion_needed(
        self, image_path: Path, mode: ModeClassification,
    ) -> AnimateResult:
        from .preprocessing import preprocess_image_simple

        out_dir = self.output_dir / "motion"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Step 0: Preprocess
        processed = out_dir / f"{image_path.stem}_processed.png"
        preprocess_image_simple(image_path, processed)

        # Step 1: Vision analysis
        analysis = self.vision_analyzer.analyze(processed)
        _log_analysis(analysis)

        # Step 2: Mask generation
        mask_path = self._generate_mask(processed, analysis)

        # Step 3: Retry loop
        retry = RetryLoop(
            config=RetryConfig(max_retries=self.max_retries),
            animation_generator=self.animation_generator,
            numerical_validator=self.numerical_validator,
            ai_validator=self.ai_validator,
            vision_analyzer=self.vision_analyzer,
            mask_generator=self.mask_generator,
        )
        gen_result = retry.run(
            image_path=processed,
            analysis=analysis,
            mask_path=mask_path,
            output_dir=out_dir,
        )

        if not gen_result.success:
            return AnimateResult(
                success=False, mode=mode, analysis=gen_result.analysis,
                attempts=gen_result.attempts,
            )

        video_path = gen_result.video_path
        final_analysis = gen_result.analysis

        # Step 4: Post-processing
        transparent, converted = self._post_process(
            video_path, final_analysis, out_dir,
        )

        # Stage 2: Post-motion classification
        post_motion = self.post_motion_classifier.classify(video_path, processed)
        kf_config = None
        if post_motion.needs_keyframe and post_motion.suggested_keyframe:
            kf_config = self.keyframe_generator.generate(
                KeyframeConfig(suggested_action=post_motion.suggested_keyframe)
            )

        return AnimateResult(
            success=True, mode=mode, video_path=video_path,
            analysis=final_analysis, attempts=gen_result.attempts,
            seed=gen_result.seed, keyframe_config=kf_config,
            transparent=transparent, converted=converted,
        )

    def _generate_mask(
        self, image: Path, analysis: VisionAnalysis,
    ) -> Path | None:
        try:
            result: Path = self.mask_generator.generate(
                image, analysis.moving_zone, self.output_dir / "masks",
            )
            return result
        except Exception as e:
            logger.warning(f"[Animate] mask generation failed: {e}")
            return None

    def _post_process(
        self, video: Path | None, analysis: VisionAnalysis | None, out_dir: Path,
    ) -> tuple[TransparentSequence | None, ConvertedAsset | None]:
        if not video or not analysis:
            return None, None

        transparent = None
        converted = None

        if analysis.bg_remove:
            try:
                transparent = self.bg_remover.remove(video)
                if transparent and transparent.frames:
                    converted = self.format_converter.convert(
                        transparent.frames, preset="web",
                    )
            except Exception as e:
                logger.warning(f"[Animate] post-process failed: {e}")

        return transparent, converted


def _log_analysis(a: VisionAnalysis) -> None:
    logger.info("  → 액션: %s", a.action_desc)
    logger.info("  → 오브젝트: %s", a.object_desc)
    logger.info("  → 움직임: %s | 고정: %s", a.moving_parts, a.fixed_parts)
    logger.info("  → fps=%d motion=%.2f~%.2f pingpong=%s", a.frame_rate, a.min_motion, a.max_motion, a.pingpong)
    logger.info("  → positive: %s", a.positive[:80])
    logger.info("  → negative: %s", a.negative[:80])
    if a.reason:
        logger.info("  → 근거: %s", a.reason[:120])
