from typing import List, Optional

from pydantic import Field

from app.models.base import RunScopedModel
from app.models.enums import ArtifactValidationStatus


class Requirement(RunScopedModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    user_problem: str = Field(min_length=1)
    description: str = Field(min_length=1)

    finding_ids: List[str]
    review_ids: List[str]

    priority: str = Field(min_length=1)
    impact: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    acceptance_criteria: List[str]
    target_version: Optional[str] = None
    assumption: bool = False
    validation_result: ArtifactValidationStatus
