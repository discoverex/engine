from __future__ import annotations

from discoverex.domain.scene import Scene
from discoverex.domain.verification import FinalVerification, VerificationResult


def run_logical_verification(scene: Scene, pass_threshold: float) -> VerificationResult:
    answer_count = len(scene.answer.answer_region_ids)
    unique_ok = answer_count == 1 and scene.answer.uniqueness_intent
    region_count = len(scene.regions)
    score = 1.0 if unique_ok else max(0.0, 0.6 - 0.1 * abs(answer_count - 1))
    signals = {
        "answer_count": answer_count,
        "uniqueness_intent": scene.answer.uniqueness_intent,
        "region_count": region_count,
    }
    return VerificationResult(
        score=score,
        pass_=score >= pass_threshold,
        signals=signals,
    )


def integrate_verification(
    logical: VerificationResult,
    perception: VerificationResult,
    pass_threshold: float,
) -> FinalVerification:
    total_score = (logical.score + perception.score) / 2.0
    passed = total_score >= pass_threshold and logical.pass_ and perception.pass_
    failure_reason = "" if passed else "score_or_component_threshold_not_met"
    return FinalVerification(
        total_score=total_score,
        pass_=passed,
        failure_reason=failure_reason,
    )
