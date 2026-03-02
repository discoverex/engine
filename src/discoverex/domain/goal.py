from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GoalType(str, Enum):
    RELATION = "relation"
    COUNT = "count"
    SHAPE = "shape"
    SEMANTIC = "semantic"


class AnswerForm(str, Enum):
    REGION_SELECT = "region_select"
    CLICK_ONE = "click_one"
    CLICK_MULTIPLE = "click_multiple"


class Goal(BaseModel):
    goal_type: GoalType
    constraint_struct: dict[str, Any] = Field(default_factory=dict)
    scope_region_ids: list[str] | None = None
    answer_form: AnswerForm
