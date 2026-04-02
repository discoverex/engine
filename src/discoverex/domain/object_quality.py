from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ObjectQualityMetrics:
    laplacian_variance: float = 0.0
    white_balance_error: float = 0.0
    mean_saturation: float = 0.0
    luma_stddev: float = 0.0


@dataclass(frozen=True)
class ObjectQualitySubscores:
    blur: float = 0.0
    white_balance: float = 0.0
    saturation: float = 0.0
    contrast: float = 0.0


@dataclass(frozen=True)
class ObjectQualityScore:
    object_index: int
    object_label: str
    object_prompt: str
    object_ref: str
    object_mask_ref: str
    raw_alpha_mask_ref: str | None = None
    mask_source: str | None = None
    metrics: ObjectQualityMetrics = field(default_factory=ObjectQualityMetrics)
    subscores: ObjectQualitySubscores = field(default_factory=ObjectQualitySubscores)
    overall_score: float = 0.0
    evaluation_image_ref: str | None = None


@dataclass(frozen=True)
class ObjectQualitySummary:
    object_count: int = 0
    mean_overall_score: float = 0.0
    min_overall_score: float = 0.0
    min_laplacian_variance: float = 0.0
    mean_white_balance_error: float = 0.0
    mean_saturation: float = 0.0
    mean_contrast: float = 0.0
    run_score: float = 0.0


@dataclass(frozen=True)
class ObjectQualityEvaluation:
    scores: list[ObjectQualityScore] = field(default_factory=list)
    summary: ObjectQualitySummary = field(default_factory=ObjectQualitySummary)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
