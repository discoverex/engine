from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    score: float
    pass_: bool = Field(alias="pass")
    signals: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class FinalVerification(BaseModel):
    total_score: float
    pass_: bool = Field(alias="pass")
    failure_reason: str

    model_config = {"populate_by_name": True}


class VerificationBundle(BaseModel):
    logical: VerificationResult
    perception: VerificationResult
    final: FinalVerification
